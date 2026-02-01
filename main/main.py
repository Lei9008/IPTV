import re
import requests
import os  # 新增：用于处理文件路径和创建文件夹

# ===================== 配置项（更新输出路径） =====================
TARGET_URLS = {
    "user_result": "https://raw.githubusercontent.com/Lei9008/iptv_selfuse/master/output/user_result.txt",
    "ku9_source": "https://raw.githubusercontent.com/Lei9008/IPTV/main/input/source/Ku9-IPTV-source.txt"
}

# 输出配置：目录 + 文件名
OUTPUT_DIR = "output"  # 输出文件夹
OUTPUT_FILENAME = "Live_iptv.txt"  # 输出文件名
# 拼接完整输出路径
OUTPUT_FILE = os.path.join(OUTPUT_DIR, OUTPUT_FILENAME)

# ===================== 核心工具函数 =====================
def fetch_github_raw_content(raw_url: str) -> str:
    """
    从GitHub Raw地址获取文件纯文本内容
    :param raw_url: GitHub文件的Raw地址
    :return: 纯文本内容（获取失败返回空字符串）
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        print(f"正在获取文件内容：{raw_url}")
        response = requests.get(raw_url, headers=headers, timeout=30)
        response.raise_for_status()  # 捕获HTTP请求错误（4xx/5xx）
        response.encoding = response.apparent_encoding or "utf-8"  # 自动识别编码，避免中文乱码
        print(f"成功获取文件内容，文件大小：{len(response.text)} 字符")
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"获取文件失败：{str(e)}")
        return ""

def parse_iptv_content(content: str) -> dict:
    """
    解析IPTV内容，优先按「频道名称,#genre#」格式分类整理
    :param content: IPTV纯文本内容
    :return: 分类字典 {分类名: [(频道名, 播放URL), ...]}
    """
    # 初始化结果字典
    genre_dict = {}
    current_genre = "未分类"  # 默认分类
    url_seen = set()  # 用于去重URL（避免相同播放地址重复添加）
    
    # 正则表达式匹配规则（优先匹配「频道名称,#genre#」格式）
    # 1. 优先匹配：频道名称,#genre#（支持前后空格，分类名提取频道名称）
    genre_pattern_main = re.compile(r'^([^,]+?)\s*,\s*#genre#\s*$', re.IGNORECASE | re.MULTILINE)
    # 2. 兼容匹配：#genre#频道名称（保留原有格式，向下兼容）
    genre_pattern_compat = re.compile(r'^#genre#\s*([^,]+?)\s*$', re.IGNORECASE | re.MULTILINE)
    # 3. 匹配频道行（格式：频道名,播放URL 或 直接播放URL（补全频道名为"未知频道"））
    channel_pattern = re.compile(r'^([^,]+),\s*(https?://[^\s]+)$', re.IGNORECASE | re.MULTILINE)
    # 4. 单独匹配播放URL（无频道名的情况）
    standalone_url_pattern = re.compile(r'^(https?://[^\s]+)$', re.IGNORECASE | re.MULTILINE)
    
    # 按行解析内容（避免整段匹配的遗漏）
    lines = content.split("\n")
    for line in lines:
        line = line.strip()
        if not line:  # 跳过空行
            continue
        
        # 第一步：优先匹配「频道名称,#genre#」格式
        genre_main_match = genre_pattern_main.match(line)
        if genre_main_match:
            current_genre = genre_main_match.group(1).strip() or "未分类"
            # 初始化该分类（若不存在）
            if current_genre not in genre_dict:
                genre_dict[current_genre] = []
            continue
        
        # 第二步：兼容匹配「#genre#频道名称」格式
        genre_compat_match = genre_pattern_compat.match(line)
        if genre_compat_match:
            current_genre = genre_compat_match.group(1).strip() or "未分类"
            # 初始化该分类（若不存在）
            if current_genre not in genre_dict:
                genre_dict[current_genre] = []
            continue
        
        # 第三步：匹配标准频道行（频道名,URL）
        channel_match = channel_pattern.match(line)
        if channel_match:
            channel_name = channel_match.group(1).strip()
            play_url = channel_match.group(2).strip()
            
            # 去重：URL已存在则跳过
            if play_url in url_seen:
                continue
            url_seen.add(play_url)
            
            # 添加到当前分类
            if current_genre not in genre_dict:
                genre_dict[current_genre] = []
            genre_dict[current_genre].append((channel_name, play_url))
            continue
        
        # 第四步：匹配单独的播放URL（补全频道名）
        url_match = standalone_url_pattern.match(line)
        if url_match:
            play_url = url_match.group(1).strip()
            
            # 去重：URL已存在则跳过
            if play_url in url_seen:
                continue
            url_seen.add(play_url)
            
            # 补全默认频道名（从URL中提取简易名称）
            channel_name = "未知频道"
            url_parts = play_url.split("/")
            for part in url_parts:
                if part and not part.startswith(("http", "www", "live", "stream", "cdn", "api")) and len(part) > 3:
                    channel_name = part
                    break
            
            # 添加到当前分类
            if current_genre not in genre_dict:
                genre_dict[current_genre] = []
            genre_dict[current_genre].append((channel_name, play_url))
            continue
    
    return genre_dict

def merge_iptv_genres(genre_dicts: list) -> dict:
    """
    合并多个分类字典，去重URL，保留所有有效分类和频道
    :param genre_dicts: 多个parse_iptv_content返回的分类字典列表
    :return: 合并后的统一分类字典
    """
    merged_dict = {}
    global_url_seen = set()  # 全局URL去重（跨文件去重）
    
    for genre_dict in genre_dicts:
        for genre_name, channel_list in genre_dict.items():
            # 初始化当前分类（若不存在于合并结果中）
            if genre_name not in merged_dict:
                merged_dict[genre_name] = []
            
            # 遍历当前分类的频道，全局去重后添加
            for channel_name, play_url in channel_list:
                if play_url not in global_url_seen:
                    global_url_seen.add(play_url)
                    merged_dict[genre_name].append((channel_name, play_url))
    
    return merged_dict

def write_merged_content(merged_dict: dict, output_file: str):
    """
    将合并后的分类内容写入输出文件，自动创建输出文件夹，分类格式统一为「频道名称,#genre#」
    :param merged_dict: 合并后的分类字典
    :param output_file: 完整输出文件路径
    """
    try:
        # 提取输出文件夹路径，自动创建（若不存在）
        output_dir = os.path.dirname(output_file)
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            print(f"已自动创建输出文件夹：{output_dir}")
        
        with open(output_file, "w", encoding="utf-8") as f:
            # 写入文件头部说明
            f.write(f"# IPTV直播源合并结果\n")
            f.write(f"# 合并来源：2个GitHub IPTV数据源\n")
            f.write(f"# 格式说明：频道名称,#genre# 对应下方该分类的所有频道（频道名,播放URL）\n")
            f.write(f"# ==============================================\n\n")
            
            # 按分类写入内容（统一使用「频道名称,#genre#」格式）
            total_channels = 0
            for genre_name, channel_list in sorted(merged_dict.items()):  # 排序输出，格式更规整
                if not channel_list:  # 跳过空分类
                    continue
                
                # 写入分类标识（统一为你指定的格式：频道名称,#genre#）
                f.write(f"{genre_name},#genre#\n")
                
                # 写入该分类下的所有频道
                for channel_name, play_url in channel_list:
                    f.write(f"{channel_name},{play_url}\n")
                
                # 分类之间添加空行，分隔更清晰
                f.write("\n")
                total_channels += len(channel_list)
            
            # 写入文件尾部统计信息
            f.write(f"# ==============================================\n")
            f.write(f"# 合并统计：共 {len(merged_dict)} 个分类，{total_channels} 个有效频道（URL已去重）\n")
        
        print(f"\n合并完成！结果已保存到：{os.path.abspath(output_file)}")
        print(f"合并统计：共 {len(merged_dict)} 个分类，{total_channels} 个有效频道（URL已去重）")
    except Exception as e:
        print(f"写入文件失败：{str(e)}")

# ===================== 主程序执行流程 =====================
def main():
    # 步骤1：获取两个文件的内容
    content_list = []
    for name, raw_url in TARGET_URLS.items():
        content = fetch_github_raw_content(raw_url)
        if content:
            content_list.append(content)
        else:
            print(f"警告：{name} 文件内容获取失败，将跳过该文件")
    
    if not content_list:
        print("错误：所有文件都获取失败，无法进行合并")
        return
    
    # 步骤2：分别解析每个文件的内容，得到分类字典列表
    genre_dict_list = []
    for content in content_list:
        genre_dict = parse_iptv_content(content)
        genre_dict_list.append(genre_dict)
    
    # 步骤3：合并所有分类字典（跨文件去重）
    merged_genre_dict = merge_iptv_genres(genre_dict_list)
    
    # 步骤4：将合并结果写入文件
    write_merged_content(merged_genre_dict, OUTPUT_FILE)

if __name__ == "__main__":
    print("===== 开始执行IPTV数据源合并程序 =====")
    main()
    print("===== 程序执行结束 =====")
