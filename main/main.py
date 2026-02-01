import requests
import os
import re

def get_url_content(url):
    """
    发送网络请求，获取指定URL的文本内容
    :param url: 目标网络链接
    :return: 链接对应的文本内容（获取失败返回空字符串）
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        response.encoding = response.apparent_encoding
        print(f"成功获取链接内容：{url}")
        return response.text
    except Exception as e:
        print(f"获取链接内容失败：{url}，错误信息：{str(e)}")
        return ""

def normalize_channel_name(channel_name):
    """
    频道名归一化，去除非字母数字的分隔符，实现近似匹配（如CCTV-1→CCTV1、CCTV 1→CCTV1）
    :param channel_name: 原始频道名
    :return: 归一化后的频道名
    """
    if not channel_name:
        return ""
    # 去除所有非字母、非数字的字符（保留中英文、数字，剔除-、_、空格、(、)等分隔符）
    normalized_name = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fff]', '', channel_name)
    # 转为大写（统一大小写，避免CCTV1和cctv1视为不同频道）
    return normalized_name.upper()

def get_channel_genre(normalized_channel_name):
    """
    根据归一化后的频道名匹配分类（#genre#），可灵活扩展分类规则
    :param normalized_channel_name: 归一化后的频道名
    :return: 对应的分类标签
    """
    # 定义分类规则（键：分类标签，值：匹配关键词列表）
    genre_rules = {
        "#央视频道#": ["CCTV", "中央"],
        "#卫视频道#": ["北京", "江苏", "浙江", "湖南", "东方", "广东", "山东", "安徽"],
        "#影视频道#": ["电影", "电视剧", "影视", "影院"],
        "#体育频道#": ["体育", "NBA", "足球", "CBA"],
        "#少儿频道#": ["少儿", "动漫", "卡通"],
        "#新闻频道#": ["新闻", "财经"],
        "#其他频道#": []  # 兜底分类
    }
    
    # 遍历分类规则，匹配对应分类
    for genre, keywords in genre_rules.items():
        if genre == "#其他频道#":
            continue
        for keyword in keywords:
            # 关键词也归一化，避免匹配偏差
            normalized_keyword = normalize_channel_name(keyword)
            if normalized_keyword in normalized_channel_name:
                return genre
    # 无匹配项返回兜底分类
    return "#其他频道#"

def parse_and_classify_iptv_content(raw_content):
    """
    解析IPTV原始内容，提取频道名和对应链接，按分类分组
    :param raw_content: 合并后的IPTV原始文本
    :return: 按分类分组的字典 {分类标签: [(频道名, 链接), ...]}
    """
    classified_channels = {}
    lines = raw_content.splitlines()
    temp_channel_name = None  # 临时存储EXTINF行的频道名（兼容标准IPTV格式）
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # 匹配标准IPTV格式：#EXTINF:-1 tvg-id="...",频道名
        if line.startswith("#EXTINF:"):
            # 提取逗号后的频道名
            comma_index = line.rfind(",")
            if comma_index != -1:
                temp_channel_name = line[comma_index+1:].strip()
            continue
        
        # 匹配普通格式：频道名,链接
        elif "," in line and not line.startswith("http"):
            parts = line.split(",", 1)  # 只分割第一个逗号，避免链接包含逗号
            channel_name = parts[0].strip()
            channel_url = parts[1].strip()
            if channel_url.startswith(("http", "rtsp", "udp")):
                # 归一化频道名并获取分类
                normalized_name = normalize_channel_name(channel_name)
                genre = get_channel_genre(normalized_name)
                # 加入分类字典
                if genre not in classified_channels:
                    classified_channels[genre] = []
                classified_channels[genre].append((channel_name, channel_url))
                temp_channel_name = None
            continue
        
        # 匹配单独的链接行（对应前面的EXTINF频道名）
        elif line.startswith(("http", "rtsp", "udp")) and temp_channel_name:
            channel_name = temp_channel_name
            channel_url = line.strip()
            # 归一化频道名并获取分类
            normalized_name = normalize_channel_name(channel_name)
            genre = get_channel_genre(normalized_name)
            # 加入分类字典
            if genre not in classified_channels:
                classified_channels[genre] = []
            classified_channels[genre].append((channel_name, channel_url))
            temp_channel_name = None
            continue
    
    return classified_channels

def merge_and_classify_iptv(url_list, save_file_path="output/Live_iptv.txt"):
    """
    合并多个URL的IPTV内容，进行频道归一化和分类汇总，保存到指定文件
    :param url_list: 待获取内容的URL列表
    :param save_file_path: 结果保存路径
    :return: 分类后的完整内容
    """
    # 1. 合并所有URL的原始内容
    merged_raw_content = ""
    for url in url_list:
        content = get_url_content(url)
        if content:
            merged_raw_content += content + "\n"
    
    if not merged_raw_content:
        print("未获取到有效IPTV内容，处理失败")
        return ""
    
    # 2. 解析并分类IPTV内容
    classified_channels = parse_and_classify_iptv_content(merged_raw_content)
    
    # 3. 整理分类结果为文本格式
    final_content = ""
    for genre, channels in sorted(classified_channels.items()):  # 排序让分类更规整
        # 写入分类标签
        final_content += f"{genre}\n"
        # 写入该分类下的所有频道（去重：基于归一化频道名和链接）
        seen = set()  # 用于去重，存储(归一化频道名, 链接)
        for channel_name, channel_url in channels:
            normalized_name = normalize_channel_name(channel_name)
            key = (normalized_name, channel_url)
            if key not in seen:
                seen.add(key)
                # 保持清晰的格式：频道名, 链接（也可改为标准IPTV格式）
                final_content += f"{channel_name},{channel_url}\n"
        # 分类之间添加空行分隔
        final_content += "\n"
    
    # 4. 保存到指定文件
    folder_path = os.path.dirname(save_file_path)
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
        print(f"成功创建文件夹：{folder_path}")
    
    with open(save_file_path, "w", encoding="utf-8") as f:
        f.write(final_content)
    print(f"处理完成，结果已保存到：{save_file_path}")
    
    return final_content

# 主程序执行
if __name__ == "__main__":
    target_urls = [
        "https://raw.githubusercontent.com/Lei9008/iptv_selfuse/master/output/user_result.txt",
        "https://raw.githubusercontent.com/Lei9008/IPTV/main/input/source/Ku9-IPTV-source.txt"
    ]
    
    merge_and_classify_iptv(target_urls)
