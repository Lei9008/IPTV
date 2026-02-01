import requests
import os

# ===================== 新增配置：GitHub 镜像/代理前缀 =====================
# 常用 GitHub RAW 镜像域名（国内可访问优先）
GITHUB_MIRRORS = [
    "raw.fastgit.org",
    "raw.gitmirror.com",
    "raw.sevencdn.com"
]

# GitHub 代理前缀（拼接在原URL前实现代理访问）
GITHUB_PROXY_PREFIXES = [
    "https://ghproxy.com/",
    "https://gh-proxy.com/",
    "https://raw.githubusercontent.com.cnpmjs.org/"
]

def replace_github_url(raw_url, use_mirror=True, use_proxy=False):
    """
    替换原GitHub RAW URL为镜像地址或添加代理前缀，提升国内访问成功率
    :param raw_url: 原始GitHub RAW URL
    :param use_mirror: 是否使用镜像域名（默认开启）
    :param use_proxy: 是否使用代理前缀（默认关闭，与镜像二选一即可）
    :return: 处理后的可访问URL
    """
    if not raw_url.startswith("https://raw.githubusercontent.com"):
        return raw_url  # 非GitHub RAW URL，直接返回
    
    new_url = raw_url
    # 1. 使用代理前缀（优先级高于镜像，二选一避免重复处理）
    if use_proxy and GITHUB_PROXY_PREFIXES:
        proxy_prefix = GITHUB_PROXY_PREFIXES[0]  # 使用第一个代理前缀（可按需切换）
        new_url = proxy_prefix + raw_url
    # 2. 使用镜像域名
    elif use_mirror and GITHUB_MIRRORS:
        mirror_domain = GITHUB_MIRRORS[0]  # 使用第一个镜像域名（可按需切换）
        new_url = raw_url.replace("raw.githubusercontent.com", mirror_domain)
    
    print(f"URL处理完成：原地址 -> {new_url}")
    return new_url

def get_url_content(url):
    """
    发送网络请求，获取指定URL的文本内容（新增GitHub地址处理）
    :param url: 目标网络链接
    :return: 链接对应的文本内容（获取失败返回空字符串）
    """
    try:
        # 先处理GitHub URL，提升访问成功率
        processed_url = replace_github_url(url)
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        response = requests.get(processed_url, headers=headers, timeout=30)
        response.raise_for_status()
        response.encoding = response.apparent_encoding
        print(f"成功获取链接内容：{processed_url}")
        return response.text
    except Exception as e:
        print(f"获取链接内容失败：{url}，错误信息：{str(e)}")
        return ""

def extract_genres_from_demo(demo_file_path="demo.txt"):
    """
    从demo.txt中提取所有#genre#标记的分类（格式：xxx,#genre#）
    :param demo_file_path: demo.txt文件路径
    :return: 提取到的分类列表（如["山东频道", "北京频道"]）
    """
    target_genres = []
    try:
        # 检查demo.txt是否存在
        if not os.path.exists(demo_file_path):
            print(f"错误：demo.txt文件不存在（路径：{demo_file_path}）")
            return target_genres
        
        # 读取demo.txt，匹配目标格式
        with open(demo_file_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()  # 去除首尾空格、换行符
                if not line:
                    continue  # 跳过空行
                
                # 匹配格式：xxx,#genre#（分割符为逗号，后部分严格等于#genre#）
                if ",#genre#" in line:
                    genre = line.split(",#genre#")[0].strip()
                    if genre:  # 避免提取空分类
                        target_genres.append(genre)
                        print(f"从demo.txt第{line_num}行提取到分类：{genre}")
    
    except Exception as e:
        print(f"读取/解析demo.txt失败，错误信息：{str(e)}")
    
    # 去重并返回（避免重复分类）
    unique_genres = list(set(target_genres))
    print(f"demo.txt分类提取完成，共获取{len(unique_genres)}个唯一分类：{unique_genres}")
    return unique_genres

def filter_content_by_genres(content, target_genres):
    """
    筛选内容，仅保留包含目标分类的行/内容（适配IPTV文本格式）
    :param content: 原始URL获取的文本内容
    :param target_genres: 从demo.txt提取的目标分类列表
    :return: 筛选后的有效内容
    """
    if not content or not target_genres:
        return ""
    
    filtered_lines = []
    # 按行分割内容（IPTV文本通常按行存储单条信息）
    lines = content.split("\n")
    for line in lines:
        line_strip = line.strip()
        # 只要该行包含任意一个目标分类，就保留（忽略空行）
        if any(genre in line_strip for genre in target_genres) and line_strip:
            filtered_lines.append(line)
    
    # 拼接筛选后的内容，保留原格式
    filtered_content = "\n".join(filtered_lines)
    print(f"内容筛选完成，保留{len(filtered_lines)}条符合分类的记录")
    return filtered_content

def merge_url_contents(url_list, save_file_path="output/Live_iptv.txt"):
    """
    合并多个URL的文本内容（仅保留匹配demo.txt分类的内容），并保存到指定本地文件路径
    :param url_list: 待获取内容的URL列表
    :param save_file_path: 合并结果保存的本地文件路径
    :return: 合并后的完整文本内容
    """
    # 第一步：先从demo.txt提取目标分类
    target_genres = extract_genres_from_demo()
    if not target_genres:
        print("未从demo.txt提取到有效分类，终止合并流程")
        return ""
    
    # 第二步：遍历URL，获取并筛选内容
    merged_content = ""
    for url in url_list:
        raw_content = get_url_content(url)
        if raw_content:
            # 筛选仅保留目标分类的内容
            filtered_content = filter_content_by_genres(raw_content, target_genres)
            if filtered_content:
                merged_content += filtered_content + "\n\n"
    
    # 第三步：保存筛选后的合并内容
    if merged_content:
        folder_path = os.path.dirname(save_file_path)
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
            print(f"成功创建文件夹：{folder_path}")
        
        with open(save_file_path, "w", encoding="utf-8") as f:
            f.write(merged_content)
        print(f"合并完成，结果已保存到：{save_file_path}")
    else:
        print("未获取到符合分类的有效内容，合并失败")
    
    return merged_content

# 主程序执行
if __name__ == "__main__":
    target_urls = [
        "https://raw.githubusercontent.com/Lei9008/IPTV/main/input/source/Ku9-IPTV-source.txt",
        "https://raw.githubusercontent.com/Lei9008/iptv_selfuse/master/output/user_result.txt"
    ]
    
    # 调用函数合并内容（自动处理GitHub镜像、提取demo分类、筛选内容）
    merge_url_contents(target_urls)
