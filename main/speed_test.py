import requests
import time
import os
import urllib3
from typing import List, Dict, Optional

# 屏蔽SSL验证警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 可选：导入tqdm实现进度条
try:
    from tqdm import tqdm
except ImportError:
    tqdm = lambda x, desc=None: x  # 兼容无tqdm环境

# ===================== 核心配置项 =====================
# 测速参数（分离连接超时和读取超时，避免卡住）
DOWNLOAD_TEST_SIZE = 1024 * 1024 * 2  # 2MB
CONNECT_TIMEOUT = 5  # 连接超时（秒）：建立网络连接的超时时间
READ_TIMEOUT = 15    # 读取超时（秒）：获取数据的超时时间
TOTAL_TIMEOUT = (CONNECT_TIMEOUT, READ_TIMEOUT)  # 组合超时（全覆盖）
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# 结果保存配置
SAVE_RESULT = True
RESULT_SAVE_PATH = "iptv_url_speed_test_result.txt"

# 流媒体协议前缀
SUPPORTED_PROTOCOLS = ["http://", "https://", "rtmp://", "rtsp://"]

# 可选：代理配置（国内访问GitHub卡顿可启用，填写你的代理地址）
USE_PROXY = False
PROXY_CONFIG = {
    "http": "http://127.0.0.1:7890",
    "https": "http://127.0.0.1:7890"
}

# ===================== 工具函数：提取所有有效流媒体链接 =====================
def extract_all_streaming_links(text_content: str) -> List[str]:
    if not text_content:
        return []
    
    streaming_links = []
    text_lines = text_content.split("\n")

    for line in text_lines:
        line = line.strip()
        if not line:
            continue
        
        for proto in SUPPORTED_PROTOCOLS:
            proto_length = len(proto)
            start_index = 0
            
            while True:
                link_start = line.find(proto, start_index)
                if link_start == -1:
                    break
                
                link_end = link_start + proto_length
                separators = [" ", ",", "\"", "'", "\t", "#", ")", "]"]
                while link_end < len(line):
                    if line[link_end] in separators:
                        break
                    link_end += 1
                
                extracted_link = line[link_start:link_end].strip()
                if len(extracted_link) > proto_length + 3:
                    streaming_links.append(extracted_link)
                
                start_index = link_end
    
    # 去重+限制数量（避免过多链接导致卡住）
    unique_links = list(dict.fromkeys(streaming_links))[:50]  # 最多提取50个链接
    return unique_links

# ===================== 工具函数：下载网络URL文件（修正url参数传递） =====================
def get_streaming_links_from_network_url(network_url: str) -> List[str]:
    print(f"📥  开始下载并解析：{network_url}")
    print(f"⌛  超时配置：连接{CONNECT_TIMEOUT}秒，读取{READ_TIMEOUT}秒")
    headers = {"User-Agent": USER_AGENT}
    
    try:
        # 配置请求参数（全覆盖超时+可选代理）
        request_kwargs = {
            "headers": headers,
            "timeout": TOTAL_TIMEOUT,
            "verify": False
        }
        if USE_PROXY:
            request_kwargs["proxies"] = PROXY_CONFIG
        
        # 修正：显式传入 url 参数（核心错误修复）
        print("🔌  正在建立网络连接...")
        response = requests.get(network_url, **request_kwargs)  # 此处添加 network_url
        print("✅  连接成功，正在获取文件内容...")
        response.raise_for_status()
        
        # 提取链接
        streaming_links = extract_all_streaming_links(response.text)
        print(f"🎉  解析完成，提取到 {len(streaming_links)} 个有效流媒体链接\n")
        return streaming_links
    
    except requests.exceptions.ConnectTimeout:
        print(f"❌  连接超时：无法在 {CONNECT_TIMEOUT} 秒内建立连接（网络阻塞或链接无效）\n")
    except requests.exceptions.ReadTimeout:
        print(f"❌  读取超时：无法在 {READ_TIMEOUT} 秒内获取文件内容（文件过大或网络缓慢）\n")
    except requests.exceptions.HTTPError as e:
        print(f"❌  HTTP错误：{e.response.status_code}\n")
    except Exception as e:
        print(f"❌  解析失败：{str(e)}\n")
    
    return []

# ===================== 核心函数：单个链接测速（修正url参数传递） =====================
def test_single_stream_link_speed(link: str) -> Optional[Dict]:
    result = {
        "link": link,
        "is_available": False,
        "response_delay_ms": 0.0,
        "download_speed_mbps": 0.0,
        "error_msg": ""
    }

    headers = {"User-Agent": USER_AGENT}
    request_kwargs = {
        "headers": headers,
        "timeout": TOTAL_TIMEOUT,
        "stream": True,
        "verify": False
    }
    if USE_PROXY:
        request_kwargs["proxies"] = PROXY_CONFIG

    try:
        # 1. 测试响应延迟（修正：传入 link 作为 url 参数）
        start_time = time.time()
        response = requests.get(link, **request_kwargs)  # 此处添加 link
        response.raise_for_status()
        end_time = time.time()

        response_delay = (end_time - start_time) * 1000
        result["response_delay_ms"] = round(response_delay, 2)
        result["is_available"] = True

        # 2. 测试下载速度（添加超时兜底）
        downloaded_size = 0
        download_start = time.time()
        chunk_size = 4096

        for chunk in response.iter_content(chunk_size=chunk_size):
            if chunk and len(chunk) > 0:
                downloaded_size += len(chunk)
            
            # 双重兜底：达到测试大小 或 超过总超时，强制退出
            if (downloaded_size >= DOWNLOAD_TEST_SIZE) or (time.time() - download_start) > READ_TIMEOUT:
                break

        download_end = time.time()
        download_duration = download_end - download_start

        if download_duration > 0.001 and downloaded_size > 0:
            downloaded_mb = downloaded_size / (1024 * 1024)
            download_speed_mbps = (downloaded_mb * 8) / download_duration
            result["download_speed_mbps"] = round(download_speed_mbps, 2)
        else:
            result["download_speed_mbps"] = 0.0
            result["error_msg"] = "未获取到有效流媒体数据"

        return result

    except requests.exceptions.ConnectTimeout:
        result["error_msg"] = f"连接超时（{CONNECT_TIMEOUT}秒内未建立连接）"
    except requests.exceptions.ReadTimeout:
        result["error_msg"] = f"读取超时（{READ_TIMEOUT}秒内未获取数据）"
    except Exception as e:
        result["error_msg"] = f"未知错误：{str(e)[:50]}"

    return result

# ===================== 核心函数：批量测速 =====================
def batch_test_stream_links(network_url_list: List[str]) -> List[Dict]:
    all_stream_links = []
    for url in network_url_list:
        # 每个URL解析前添加分隔符，明确进度
        print("="*60)
        links = get_streaming_links_from_network_url(url)
        all_stream_links.extend(links)
    
    unique_stream_links = list(dict.fromkeys(all_stream_links))
    if not unique_stream_links:
        print("❌  无有效待测速链接，终止测速")
        return []

    print(f"🚀  开始批量测速（共 {len(unique_stream_links)} 个链接，单个链接超时{sum(TOTAL_TIMEOUT)}秒）\n")
    speed_results = []

    for idx, link in enumerate(tqdm(unique_stream_links, desc="测速进度"), 1):
        # 每10个链接添加一次进度反馈，避免看起来不动
        if idx % 10 == 0:
            print(f"🔄  已完成 {idx}/{len(unique_stream_links)} 个链接测速...")
        
        test_result = test_single_stream_link_speed(link)
        if test_result:
            speed_results.append(test_result)

    # 排序
    speed_results.sort(
        key=lambda x: (x["is_available"], x["download_speed_mbps"], -x["response_delay_ms"]),
        reverse=True
    )

    return speed_results

# ===================== 工具函数：打印并保存结果 =====================
def print_and_save_speed_results(speed_results: List[Dict]):
    if not speed_results:
        print("❌  无测速结果可展示")
        return

    print("\n" + "="*120)
    print("📊  流媒体链接测速结果汇总")
    print("="*120)
    print(f"{'序号':<4} {'可用状态':<8} {'延迟(ms)':<12} {'下载速度(Mbps)':<18} {'链接简要信息'}")
    print("-"*120)

    save_content = [
        "流媒体链接测速结果汇总",
        f"测速时间：{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}",
        f"超时配置：连接{CONNECT_TIMEOUT}秒，读取{READ_TIMEOUT}秒",
        "="*120,
        f"{'序号':<4} {'可用状态':<8} {'延迟(ms)':<12} {'下载速度(Mbps)':<18} {'完整链接'} | 错误信息",
        "-"*120
    ]

    for idx, result in enumerate(speed_results, 1):
        available_status = "✅ 可用" if result["is_available"] else "❌ 不可用"
        delay = result["response_delay_ms"]
        download_speed = result["download_speed_mbps"]
        link = result["link"]
        error_msg = result["error_msg"]
        link_brief = link[:60] + "..." if len(link) > 60 else link

        print(f"{idx:<4} {available_status:<8} {delay:<12} {download_speed:<18} {link_brief}")
        save_line = f"{idx:<4} {available_status:<8} {delay:<12} {download_speed:<18} {link} | {error_msg}"
        save_content.append(save_line)

    if SAVE_RESULT:
        try:
            save_folder = os.path.dirname(RESULT_SAVE_PATH)
            if save_folder and not os.path.exists(save_folder):
                os.makedirs(save_folder)
            
            with open(RESULT_SAVE_PATH, "w", encoding="utf-8") as f:
                f.write("\n".join(save_content))
            
            print(f"\n🎉  测速结果已保存到：{os.path.abspath(RESULT_SAVE_PATH)}")
        except Exception as e:
            print(f"\n❌  保存结果失败：{str(e)}")

# ===================== 主程序入口 =====================
if __name__ == "__main__":
    # 配置目标URL
    TARGET_NETWORK_URLS = [
        "https://raw.githubusercontent.com/Lei9008/IPTV/main/input/source/movie.txt"
    ]

    # 打印启动信息，避免假死
    print("="*80)
    print("🚀  IPTV 流媒体链接测速脚本启动")
    print("="*80)
    start_total_time = time.time()

    # 批量测速
    final_test_results = batch_test_stream_links(TARGET_NETWORK_URLS)

    # 打印结果
    print_and_save_speed_results(final_test_results)

    # 总耗时反馈
    total_duration = time.time() - start_total_time
    print(f"\n⏱️  脚本总运行时间：{round(total_duration, 2)} 秒")
