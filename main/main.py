import requests
import os

# ===================== 配置项：GitHub 镜像/代理前缀 + 匹配模式（可按需更新） =====================
# 常用 GitHub RAW 镜像域名（国内可访问优先）
GITHUB_MIRRORS = [
    "raw.gitmirror.com",
    "raw.sevencdn.com",
    "raw.kkgithub.com"
]

# GitHub 代理前缀（拼接在原URL前实现代理访问）
GITHUB_PROXY_PREFIXES = [
    "https://ghproxy.com/",
    "https://gh-proxy.com/",
    "https://raw.githubusercontent.com.cnpmjs.org/"
]

# demo.txt 匹配模式配置：True=精准匹配（推荐），False=模糊匹配（兼容旧版）
# 精准匹配：仅匹配 IPTV 行中 ",#genre#" 前的分类与 demo.txt 分类完全一致
# 模糊匹配：只要 IPTV 行中包含 demo.txt 分类即保留（可能有无关内容误匹配）
ACCURATE_MATCH_MODE = True

# ===================== 工具函数：GitHub URL 处理（拆分镜像/代理 + 格式校验） =====================
def get_mirror_url(raw_url):
    """
    生成镜像域名的URL（仅处理GitHub RAW地址，增加格式校验）
    :param raw_url: 原始GitHub RAW URL
    :return: 镜像处理后的URL
    """
    # 增加URL格式校验，提示用户正确格式
    if not raw_url.startswith("https://raw.githubusercontent.com"):
        print(f"⚠️  警告：URL格式错误，仅支持 GitHub RAW 地址（以 https://raw.githubusercontent.com 开头）")
        print(f"❌  当前错误URL：{raw_url}")
        return raw_url
    
    if GITHUB_MIRRORS:
        mirror_domain = GITHUB_MIRRORS[0]
        mirror_url = raw_url.replace("raw.githubusercontent.com", mirror_domain)
        print(f"✅  生成镜像URL：{raw_url} -> {mirror_url}")
        return mirror_url
    return raw_url

def get_proxy_url(raw_url):
    """
    生成带代理前缀的URL（仅处理GitHub RAW地址，增加格式校验）
    :param raw_url: 原始GitHub RAW URL
    :return: 代理处理后的URL
    """
    # 增加URL格式校验，提示用户正确格式
    if not raw_url.startswith("https://raw.githubusercontent.com"):
        print(f"⚠️  警告：URL格式错误，仅支持 GitHub RAW 地址（以 https://raw.githubusercontent.com 开头）")
        print(f"❌  当前错误URL：{raw_url}")
        return raw_url
    
    if GITHUB_PROXY_PREFIXES:
        proxy_prefix = GITHUB_PROXY_PREFIXES[0]
        proxy_url = proxy_prefix + raw_url
        print(f"✅  生成代理URL：{raw_url} -> {proxy_url}")
        return proxy_url
    return raw_url

# ===================== 工具函数：发送请求（独立封装，方便重试） =====================
def send_request(target_url):
    """
    发送GET请求，返回文本内容（失败返回None）
    :param target_url: 目标访问URL
    :return: 文本内容 / None
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        response = requests.get(target_url, headers=headers, timeout=30)
        response.raise_for_status()
        response.encoding = response.apparent_encoding
        print(f"🎉  成功获取链接内容：{target_url}")
        return response.text
    except Exception as e:
        print(f"❌  访问失败：{target_url}，错误信息：{str(e)}")
        return None

# ===================== 工具函数：获取单个URL文本内容（实现镜像→代理自动重试） =====================
def get_url_content(url):
    """
    发送网络请求，获取指定URL的文本内容（优先镜像，失败自动切换代理重试）
    :param url: 目标网络链接
    :return: 链接对应的文本内容（获取失败返回空字符串）
    """
    # 第一步：优先尝试镜像模式访问
    mirror_url = get_mirror_url(url)
    content = send_request(mirror_url)
    
    # 第二步：如果镜像访问失败，切换为代理模式重试
    if content is None:
        print("\n--- 📌 镜像访问失败，尝试切换为代理模式重试 ---")
        proxy_url = get_proxy_url(url)
        content = send_request(proxy_url)
    
    # 第三步：返回结果（无论是否成功，统一处理为字符串，避免None）
    return content if content is not None else ""

# ===================== 新增：demo.txt 辅助工具（格式规范 + 分类解析） =====================
def normalize_genre(genre):
    """
    分类标准化处理（去除前后空格、转为统一大小写，避免因格式差异导致匹配失败）
    :param genre: 原始分类字符串
    :return: 标准化后的分类字符串
    """
    # 去除前后空格，转为小写（不区分大小写匹配，提升易用性）
    return genre.strip().lower()

def parse_single_demo_line(line):
    """
    解析 demo.txt 单行内容，提取有效分类（支持注释、纯分类、带,#genre#格式）
    :param line: demo.txt 单行文本
    :return: 有效分类（无有效分类返回None）
    """
    line = line.strip()
    
    # 1. 忽略空行和注释行（以 # 开头的视为注释）
    if not line or line.startswith("#"):
        return None
    
    # 2. 解析带 ,#genre# 格式的行（兼容旧版 demo.txt）
    if ",#genre#" in line:
        genre = line.split(",#genre#")[0]
        normalized_genre = normalize_genre(genre)
        return normalized_genre if normalized_genre else None
    
    # 3. 解析纯分类行（新增：支持直接写分类，无需拼接 ,#genre#）
    normalized_genre = normalize_genre(line)
    return normalized_genre if normalized_genre else None

# ===================== 优化：demo.txt 分类提取（增强格式支持 + 标准化） =====================
def extract_genres_from_demo(demo_file_name="demo.txt"):
    """
    从与main.py同级的demo.txt中提取有效分类（支持多种格式，自动标准化去重）
    :param demo_file_name: demo.txt文件名
    :return: 提取到的唯一、标准化分类列表
    """
    target_genres = []
    try:
        # 直接获取main.py所在目录（即demo.txt所在目录）
        script_dir = os.path.dirname(os.path.abspath(__file__))
        demo_file_path = os.path.join(script_dir, demo_file_name)
        
        if not os.path.exists(demo_file_path):
            print(f"❌  错误：demo.txt文件不存在（路径：{demo_file_path}）")
            print(f"📌  请将demo.txt放在main.py同级目录：{script_dir}")
            print(f"📌  demo.txt支持格式：1. 纯分类（如：综艺频道） 2. 带标记（如：综艺频道,#genre#） 3. 注释（以#开头）")
            return target_genres
        
        # 读取并逐行解析分类
        with open(demo_file_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                genre = parse_single_demo_line(line)
                if genre:
                    target_genres.append(genre)
                    print(f"📌  从demo.txt第{line_num}行提取到分类：{genre}（原始行：{line.strip()}）")
    
    except Exception as e:
        print(f"❌  读取/解析demo.txt失败，错误信息：{str(e)}")
    
    # 去重并返回（标准化后去重，避免重复匹配）
    unique_genres = list(set(target_genres))
    print(f"\n🎉  demo.txt分类提取完成，共获取{len(unique_genres)}个唯一标准化分类：{unique_genres}")
    return unique_genres

# ===================== 新增：精准/模糊匹配核心逻辑 =====================
def is_line_match_genre(line, target_genres):
    """
    判断单条IPTV行是否匹配目标分类（支持精准/模糊两种模式）
    :param line: IPTV单行内容
    :param target_genres: 标准化后的目标分类列表
    :return: 匹配返回True，不匹配返回False
    """
    line_strip = line.strip()
    if not line_strip or not target_genres:
        return False
    
    # 标准化行内容（用于不区分大小写匹配）
    line_normalized = line_strip.lower()
    
    if ACCURATE_MATCH_MODE:
        # 精准匹配：仅提取 IPTV 行中 ,#genre# 前的分类，与目标分类完全一致
        if ",#genre#" in line_normalized:
            line_genre = line_normalized.split(",#genre#")[0].strip()
            # 检查提取的分类是否在目标分类列表中
            return line_genre in target_genres
        else:
            # 无 ,#genre# 标记的行，精准匹配模式下忽略
            return False
    else:
        # 模糊匹配：只要行内容包含任意目标分类即匹配（兼容旧版逻辑）
        return any(genre in line_normalized for genre in target_genres)

# ===================== 优化：按分类筛选内容（新增精准/模糊匹配开关） =====================
def filter_content_by_genres(content, target_genres):
    """
    筛选内容，仅保留包含目标分类的行（支持精准/模糊匹配，保留原格式）
    :param content: 原始URL获取的文本内容
    :param target_genres: 从demo.txt提取的标准化目标分类列表
    :return: 筛选后的有效内容
    """
    if not content or not target_genres:
        return ""
    
    filtered_lines = []
    lines = content.split("\n")
    match_mode = "精准匹配" if ACCURATE_MATCH_MODE else "模糊匹配"
    print(f"📌  当前使用 {match_mode} 模式筛选内容...")
    
    for line in lines:
        if is_line_match_genre(line, target_genres):
            filtered_lines.append(line)
    
    filtered_content = "\n".join(filtered_lines)
    print(f"🎉  内容筛选完成，保留{len(filtered_lines)}条符合分类的记录\n")
    return filtered_content

# ===================== 核心函数：合并并保存筛选后的内容 =====================
def merge_url_contents(url_list, save_file_path="output/Live_iptv.txt"):
    """
    合并多个URL的文本内容（仅保留匹配demo.txt分类的内容），并保存到本地
    :param url_list: 待获取内容的URL列表
    :param save_file_path: 合并结果保存路径
    :return: 合并后的完整文本内容
    """
    # 第一步：提取目标分类（无有效分类则终止）
    target_genres = extract_genres_from_demo()
    if not target_genres:
        print("❌  未提取到有效分类，终止合并流程")
        return ""
    
    # 第二步：遍历URL，获取并筛选内容
    merged_content = ""
    for url in url_list:
        print(f"\n--- 📌 开始处理URL：{url} ---")
        raw_content = get_url_content(url)
        if raw_content:
            filtered_content = filter_content_by_genres(raw_content, target_genres)
            if filtered_content:
                merged_content += filtered_content + "\n\n"
    
    # 第三步：保存合并结果
    if merged_content:
        # 自动创建文件夹
        folder_path = os.path.dirname(save_file_path)
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
            print(f"🎉  成功创建文件夹：{folder_path}")
        
        # 写入文件（UTF-8编码避免乱码）
        with open(save_file_path, "w", encoding="utf-8") as f:
            f.write(merged_content)
        print(f"\n🎉  合并完成，结果已保存到：{os.path.abspath(save_file_path)}")
    else:
        print("\n❌  未获取到符合分类的有效内容，合并失败")
    
    return merged_content

# ===================== 主程序入口（已修正正确的GitHub RAW地址） =====================
if __name__ == "__main__":
    # 目标IPTV数据源URL列表（正确的GitHub RAW地址，可直接抓取纯文本）
    target_urls = [
        "https://raw.githubusercontent.com/Lei9008/IPTV/main/input/source/Ku9-IPTV-source.txt",
        "https://raw.githubusercontent.com/Lei9008/iptv_selfuse/master/output/user_result.txt"
    ]
    
    # 调用核心合并函数
    merge_url_contents(target_urls)
