import requests
import time
import os
import urllib3
from typing import List, Dict, Optional

# 屏蔽SSL验证警告（适配部分私有流媒体服务器）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 可选：导入tqdm实现进度条（未安装不影响核心功能）
try:
    from tqdm import tqdm
except ImportError:
    tqdm = lambda x, desc=None: x  # 兼容无tqdm的环境

# ===================== 核心配置项（按需调整） =====================
# 测速参数
DOWNLOAD_TEST_SIZE = 1024 * 1024 * 2  # 2MB，兼顾测速精准度和耗时
TIMEOUT = 20  # 网络请求超时时间（秒），网络差可适当调大
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# 结果保存配置
SAVE_RESULT = True
RESULT_SAVE_PATH = "iptv_url_speed_test_result.txt"

# 流媒体协议前缀（支持的链接格式，可扩展）
SUPPORTED_PROTOCOLS = [
    "http://",
    "https://",
    "rtmp://",
    "rtsp://",
    "mms://",
    "hls://"
]

# ===================== 工具函数：从文本中提取所有有效流媒体链接 =====================
def extract_all_streaming_links(text_content: str) -> List[str]:
    """
    从任意文本内容中，提取所有支持的流媒体链接（核心：不限制格式，只匹配协议前缀）
    :param text_content: 网络文件下载的原始文本内容
    :return: 去重后的有效流媒体链接列表
    """
    if not text_content:
        return []
    
    streaming_links = []
    text_lines = text_content.split("\n")

    # 遍历每一行，提取所有符合协议前缀的链接
    for line in text_lines:
        line = line.strip()
        if not line:
            continue
        
        # 遍历所有支持的协议，提取完整链接
        for proto in SUPPORTED_PROTOCOLS:
            proto_length = len(proto)
            start_index = 0
            
            # 一行中可能包含多个链接，循环提取
            while True:
                # 查找当前协议在该行的起始位置
                link_start = line.find(proto, start_index)
                if link_start == -1:
                    break  # 无更多该协议链接，切换下一个协议
                
                # 提取链接结束位置（遇到分隔符即停止）
                link_end = link_start + proto_length
                separators = [" ", ",", "\"", "'", "\t", "#", ")", "]", ";", "<", ">"]
                while link_end < len(line):
                    if line[link_end] in separators:
                        break
                    link_end += 1
                
                # 提取并验证链接（至少包含协议+域名，避免无效短链接）
                extracted_link = line[link_start:link_end].strip()
                if len(extracted_link) > proto_length + 3:  # 至少 proto://xxx 格式
                    streaming_links.append(extracted_link)
                
                # 更新起始位置，继续查找该行剩余的同协议链接
                start_index = link_end
    
    # 去重（保持链接提取顺序，避免重复测速）
    unique_links = list(dict.fromkeys(streaming_links))
    return unique_links

# ===================== 工具函数：下载网络URL文件并提取流媒体链接 =====================
def get_streaming_links_from_network_url(network_url: str) -> List[str]:
    """
    下载指定网络URL的文件内容，提取其中所有有效流媒体链接
    :param network_url: 网络文件URL（如GitHub RAW、公共IPTV列表URL等）
    :return: 待测速的流媒体链接列表
    """
    print(f"📥  开始下载并解析网络文件：{network_url}")
    headers = {"User-Agent": USER_AGENT}
    
    try:
        # 下载网络文件内容
        response = requests.get(
            network_url,
            headers=headers,
            timeout=TIMEOUT,
            verify=False
        )
        response.raise_for_status()  # 捕获HTTP错误（404/500等）
        print(f"✅  网络文件下载成功，开始提取流媒体链接...")
        
        # 提取所有有效流媒体链接
        streaming_links = extract_all_streaming_links(response.text)
        print(f"🎉  链接提取完成，共获取 {len(streaming_links)} 个有效流媒体链接\n")
        return streaming_links
    
    except requests.exceptions.Timeout:
        print(f"❌  下载超时：{network_url}（超时时间：{TIMEOUT}秒）")
    except requests.exceptions.HTTPError as e:
        print(f"❌  HTTP错误：{network_url}，错误码：{e.response.status_code}")
    except Exception as e:
        print(f"❌  解析失败：{network_url}，错误信息：{str(e)}")
    
    return []

# ===================== 核心函数：单个流媒体链接测速 =====================
def test_single_stream_link_speed(link: str) -> Optional[Dict]:
    """
    测试单个流媒体链接的连通性、延迟和下载速度
    :param link: 有效流媒体链接
    :return: 测速结果字典（失败返回None）
    """
    result = {
        "link": link,
        "is_available": False,
        "response_delay_ms": 0.0,
        "download_speed_mbps": 0.0,
        "error_msg": ""
    }

    headers = {"User-Agent": USER_AGENT}

    try:
        # 1. 测试响应延迟（建立连接+获取响应头耗时）
        start_time = time.time()
        response = requests.get(
            link,
            headers=headers,
            timeout=TIMEOUT,
            stream=True,
            verify=False
        )
        response.raise_for_status()
        end_time = time.time()

        # 计算延迟（毫秒）
        response_delay = (end_time - start_time) * 1000
        result["response_delay_ms"] = round(response_delay, 2)
        result["is_available"] = True

        # 2. 测试下载速度（拉取指定大小的流媒体数据）
        downloaded_size = 0
        download_start = time.time()
        chunk_size = 4096  # 调大分片大小，提升流媒体拉取效率

        for chunk in response.iter_content(chunk_size=chunk_size):
            if chunk and len(chunk) > 0:  # 过滤空分片，避免无效数据统计
                downloaded_size += len(chunk)
                # 达到测试大小或超时，终止拉取
                if (downloaded_size >= DOWNLOAD_TEST_SIZE) or (time.time() - download_start) > TIMEOUT:
                    break

        download_end = time.time()
        download_duration = download_end - download_start

        # 计算下载速度（Mbps，避免除以零错误）
        if download_duration > 0.001 and downloaded_size > 0:
            downloaded_mb = downloaded_size / (1024 * 1024)
            download_speed_mbps = (downloaded_mb * 8) / download_duration
            result["download_speed_mbps"] = round(download_speed_mbps, 2)
        else:
            result["download_speed_mbps"] = 0.0
            result["error_msg"] = "未获取到有效流媒体数据（服务器限制或非直播流）"

        return result

    except requests.exceptions.Timeout:
        result["error_msg"] = "请求超时（链接失效或网络较差）"
    except requests.exceptions.HTTPError as e:
        result["error_msg"] = f"HTTP错误：{str(e)}"
    except Exception as e:
        result["error_msg"] = f"未知错误：{str(e)}"

    return result

# ===================== 核心函数：批量流媒体链接测速 =====================
def batch_test_stream_links(network_url_list: List[str]) -> List[Dict]:
    """
    批量处理网络URL，提取流媒体链接并完成测速，返回排序后的结果
    :param network_url_list: 网络文件URL列表
    :return: 按下载速度降序排序的测速结果列表
    """
    # 第一步：提取所有网络URL中的流媒体链接
    all_stream_links = []
    for url in network_url_list:
        links = get_streaming_links_from_network_url(url)
        all_stream_links.extend(links)
    
    # 去重，避免重复测速
    unique_stream_links = list(dict.fromkeys(all_stream_links))
    if not unique_stream_links:
        print("❌  无有效待测速流媒体链接，终止测速流程")
        return []

    # 第二步：批量测速
    print(f"🚀  开始批量测速（共 {len(unique_stream_links)} 个链接，耐心等待...）\n")
    speed_results = []

    for link in tqdm(unique_stream_links, desc="测速进度"):
        test_result = test_single_stream_link_speed(link)
        if test_result:
            speed_results.append(test_result)

    # 第三步：排序（可用状态→下载速度降序→延迟升序）
    speed_results.sort(
        key=lambda x: (x["is_available"], x["download_speed_mbps"], -x["response_delay_ms"]),
        reverse=True
    )

    return speed_results

# ===================== 工具函数：打印并保存测速结果 =====================
def print_and_save_speed_results(speed_results: List[Dict]):
    """
    打印控制台结果，并保存到本地文件（UTF-8编码避免乱码）
    """
    if not speed_results:
        print("❌  无测速结果可展示")
        return

    # 整理控制台输出内容
    print("\n" + "="*120)
    print("📊  流媒体链接测速结果汇总（按下载速度从快到慢排序）")
    print("="*120)
    print(f"{'序号':<4} {'可用状态':<8} {'延迟(ms)':<12} {'下载速度(Mbps)':<18} {'链接简要信息'}")
    print("-"*120)

    # 整理文件保存内容
    save_content = [
        "流媒体链接测速结果汇总",
        f"测速时间：{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}",
        f"配置参数：下载测试大小={DOWNLOAD_TEST_SIZE/(1024*1024)}MB，超时时间={TIMEOUT}秒",
        "="*120,
        f"{'序号':<4} {'可用状态':<8} {'延迟(ms)':<12} {'下载速度(Mbps)':<18} {'完整链接'} | 错误信息",
        "-"*120
    ]

    # 遍历结果填充内容
    for idx, result in enumerate(speed_results, 1):
        available_status = "✅ 可用" if result["is_available"] else "❌ 不可用"
        delay = result["response_delay_ms"]
        download_speed = result["download_speed_mbps"]
        link = result["link"]
        error_msg = result["error_msg"]
        link_brief = link[:60] + "..." if len(link) > 60 else link

        # 打印到控制台
        print(f"{idx:<4} {available_status:<8} {delay:<12} {download_speed:<18} {link_brief}")

        # 添加到保存内容
        save_line = f"{idx:<4} {available_status:<8} {delay:<12} {download_speed:<18} {link} | {error_msg}"
        save_content.append(save_line)

    # 保存到本地文件
    if SAVE_RESULT:
        try:
            # 自动创建文件夹（若不存在）
            save_folder = os.path.dirname(RESULT_SAVE_PATH)
            if save_folder and not os.path.exists(save_folder):
                os.makedirs(save_folder)
            
            with open(RESULT_SAVE_PATH, "w", encoding="utf-8") as f:
                f.write("\n".join(save_content))
            
            print(f"\n🎉  测速结果已保存到：{os.path.abspath(RESULT_SAVE_PATH)}")
        except Exception as e:
            print(f"\n❌  保存结果失败，错误信息：{str(e)}")

# ===================== 主程序入口（直接配置网络URL即可运行） =====================
if __name__ == "__main__":
    # 配置需要解析的网络URL列表（可添加多个，支持GitHub RAW、公共IPTV列表等）
    TARGET_NETWORK_URLS = [
        # 核心测试目标：Lei9008/IPTV 的 movie.txt
        "https://raw.githubusercontent.com/Lei9008/IPTV/main/input/source/movie.txt",
        # 可选：添加其他IPTV列表URL
        # "https://example.com/iptv/playlist.m3u8"
    ]

    # 步骤1：批量提取链接并测速
    final_test_results = batch_test_stream_links(TARGET_NETWORK_URLS)

    # 步骤2：打印并保存结果
    print_and_save_speed_results(final_test_results)
