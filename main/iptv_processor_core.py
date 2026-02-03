import requests
import subprocess
from concurrent.futures import ThreadPoolExecutor  # 多线程提速

# 配置项（按需改）
M3U_URL = "https://raw.githubusercontent.com/Lei9008/IPTV/main/input/source/movie.txt"  # 你的外部数据URL
THREAD_NUM = 10                                # 并发线程数（越多越快，别超20）
REQUEST_TIMEOUT = 5                            # HTTP请求超时时间（秒）
FFMPEG_TIMEOUT = 10                            # ffmpeg测试超时时间（秒）
OUTPUT_FILE = "可用电影点播.txt"                 # 最终保存有效结果的文件

# 测试单个链接是否可用+能播放
def test_stream(url):
    try:
        # 第一步：测试链接连通性（head请求更轻量）
        resp = requests.head(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        if resp.status_code != 200:
            return False
        
        # 第二步：用ffmpeg测试能否播放（关键）
        cmd = ["ffmpeg", "-v", "error", "-i", url, "-t", "1", "-f", "null", "-"]
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=FFMPEG_TIMEOUT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return result.returncode == 0
    except Exception as e:
        # 捕获所有异常，直接返回不可用
        return False

# 从外部URL提取「电影名字-播放URL」键值对（适配你的特定逗号分隔格式）
def get_name_url_from_remote_url(remote_url):
    name_url_dict = {}
    
    try:
        # 下载远程数据内容
        resp = requests.get(remote_url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        resp.raise_for_status()  # 若HTTP请求失败（非200），抛出异常
        content_lines = resp.text.splitlines()  # 按行分割内容
        
        # 解析特定格式：每行「名字,URL」，跳过首行分类（包含#genre#）和异常行
        for line in content_lines:
            line = line.strip()
            if not line:
                continue  # 跳过空行
            
            # 跳过分类行（包含#genre#，如"电影点播,#genre#"）
            if "#genre#" in line:
                continue
            
            # 按逗号分割，提取名字和URL（适配你的核心格式）
            if "," in line:
                # 分割为两部分：避免电影名字中包含逗号的情况（取最后一个逗号前为名字，后为URL）
                parts = line.rsplit(",", 1)
                movie_name = parts[0].strip()
                movie_url = parts[1].strip()
                
                # 验证URL是否为有效m3u8链接（简单过滤，避免无效数据）
                if movie_url.startswith("http") and (".m3u8" in movie_url):
                    # 避免重复URL覆盖（若有重复，保留第一个）
                    if movie_url not in name_url_dict.values():
                        name_url_dict[movie_name] = movie_url
            else:
                # 无逗号的行，视为无效数据，跳过
                continue
    
    except Exception as e:
        raise Exception(f"下载或解析远程数据失败：{str(e)[:50]}")
    
    return name_url_dict

# 批量执行测试，仅保留有效结果
def batch_test_and_save(name_url_dict):
    if not name_url_dict:
        print("❌ 未提取到任何有效电影点播流（名字+URL）")
        return
    
    valid_results = []  # 存储可正常播放的（名字，URL）
    names = list(name_url_dict.keys())
    urls = list(name_url_dict.values())
    
    print(f"📊 共检测到 {len(urls)} 个电影点播链接，开始并发测试...\n")
    
    # 多线程并发测试
    with ThreadPoolExecutor(max_workers=THREAD_NUM) as executor:
        test_results = executor.map(test_stream, urls)
    
    # 筛选有效结果（仅保留可正常播放的）
    for name, url, is_valid in zip(names, urls, test_results):
        if is_valid:
            valid_results.append((name, url))
            print(f"✅ 可播放 | {name} | {url}")
        else:
            print(f"❌ 不可用 | {name} | {url}")
    
    # 保存有效结果到文件
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for name, url in valid_results:
            f.write(f"{name} | {url}\n")
    
    print(f"\n✅ 测试完成！共筛选出 {len(valid_results)} 个可用电影点播流")
    print(f"📁 有效结果已保存到【{OUTPUT_FILE}】")

# 主程序入口
if __name__ == "__main__":
    try:
        # 步骤1：从远程URL提取电影名字和播放URL（适配新格式）
        name_url_map = get_name_url_from_remote_url(M3U_URL)
        
        # 步骤2：批量测试并保存有效结果
        batch_test_and_save(name_url_map)
    
    except Exception as e:
        print(f"❌ 程序运行失败：{e}")
