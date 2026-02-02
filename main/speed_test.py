import requests
import time
import os
import urllib3
from typing import List, Dict, Optional

# 屏蔽SSL验证警告（适配部分流媒体链接）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 可选：导入tqdm实现进度条（未安装可注释掉，不影响核心功能）
try:
    from tqdm import tqdm
except ImportError:
    tqdm = lambda x, desc=None: x  # 兼容未安装tqdm的情况，定义空实现

# ===================== 配置项（可按需调整） =====================
# 测速参数
DOWNLOAD_TEST_SIZE = 1024 * 1024 * 2  # 优化：调整为2MB，兼顾精准度和耗时
TIMEOUT = 20  # 优化：延长超时时间至20秒，适配网络较差场景
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# 结果保存配置
SAVE_RESULT = True
RESULT_SAVE_PATH = "iptv_speed_test_result.txt"

# ===================== 工具函数：解析IPTV文本（适配m3u/m3u8/txt格式，含movie.txt） =====================
def parse_iptv_content(iptv_content: str) -> List[str]:
    """
    优化：解析 m3u/m3u8/txt 格式 IPTV 内容，提取有效的流媒体链接（适配 movie.txt 格式）
    :param iptv_content: IPTV 文本内容
    :return: 提取到的流媒体链接列表
    """
    iptv_links = []
    lines = iptv_content.split("\n")
    for line in lines:
        line = line.strip()
        # 筛选条件优化：支持 http/https/rtmp 开头，排除注释、空行、纯文本分类
        if line and not line.startswith(("#", ",", "【", "】")) and (
            line.startswith("http://") or line.startswith("https://") or line.startswith("rtmp://")
        ):
            iptv_links.append(line)
    return iptv_links

def get_iptv_links_from_input(input_links: List[str]) -> List[str]:
    """
    优化：处理输入链接列表，自动解析 m3u/m3u8/txt 链接，返回最终待测速的流媒体链接列表
    :param input_links: 输入的原始链接列表
    :return: 待测速的纯流媒体链接列表
    """
    final_links = []
    headers = {"User-Agent": USER_AGENT}

    for link in input_links:
        link = link.strip()
        if not link:
            continue

        # 优化：支持 .txt 后缀链接（适配 movie.txt 这类 IPTV 源文件）
        if link.endswith((".m3u", ".m3u8", ".txt")):
            try:
                # 优化：添加 verify=False 跳过 SSL 验证，解决部分链接访问问题
                response = requests.get(
                    link, 
                    headers=headers, 
                    timeout=TIMEOUT, 
                    verify=False
                )
                response.raise_for_status()
                # 统一调用优化后的解析函数
                iptv_links = parse_iptv_content(response.text)
                final_links.extend(iptv_links)
                print(f"✅  解析成功，提取到 {len(iptv_links)} 个流媒体链接：{link}")
            except Exception as e:
                print(f"❌  解析失败，跳过：{link}，错误：{str(e)}")
        else:
            # 普通流媒体链接，直接加入列表
            final_links.append(link)

    # 去重，避免重复测速（保持链接顺序）
    final_unique_links = list(dict.fromkeys(final_links))
    print(f"\n🎉  链接处理完成，共获取 {len(final_unique_links)} 个唯一待测速IPTV链接\n")
    return final_unique_links

# ===================== 核心函数：单个IPTV链接测速（优化流媒体拉取逻辑） =====================
def test_single_iptv_speed(link: str) -> Optional[Dict]:
    """
    优化：测试单个IPTV链接的速度，适配流媒体分片拉取，返回准确测速结果
    :param link: 单个IPTV流媒体链接
    :return: 测速结果字典（失败返回None）
    """
    result = {
        "link": link,
        "is_available": False,
        "response_delay_ms": 0,
        "download_speed_mbps": 0.0,
        "error_msg": ""
    }

    headers = {"User-Agent": USER_AGENT}

    try:
        # 1. 测试响应延迟（首次建立连接+获取响应头耗时）
        start_time = time.time()
        # 优化：优先 GET 请求（带 stream=True），适配更多流媒体服务器（部分不支持 HEAD）
        response = requests.get(
            link, 
            headers=headers, 
            timeout=TIMEOUT, 
            stream=True, 
            verify=False
        )
        response.raise_for_status()
        end_time = time.time()

        response_delay = (end_time - start_time) * 1000  # 转为毫秒
        result["response_delay_ms"] = round(response_delay, 2)
        result["is_available"] = True

        # 2. 测试下载速度（优化：调大分片大小，提升流媒体拉取效率）
        downloaded_size = 0
        download_start_time = time.time()
        chunk_size = 4096  # 优化：从 1024 调整为 4096 字节，适配流媒体分片

        for chunk in response.iter_content(chunk_size=chunk_size):
            if chunk and len(chunk) > 0:  # 优化：增加数据有效性判断，过滤空分片
                downloaded_size += len(chunk)
                # 双重判断：达到测试大小 或 超时，终止拉取（避免无限等待）
                if (downloaded_size >= DOWNLOAD_TEST_SIZE) or (time.time() - download_start_time) > TIMEOUT:
                    break

        download_end_time = time.time()
        download_duration = download_end_time - download_start_time

        # 优化：完善下载速度计算逻辑，避免除以零错误
        if download_duration > 0.001 and downloaded_size > 0:
            # 转为 MB（字节）
            downloaded_mb = downloaded_size / (1024 * 1024)
            # 转为 Mbps（兆比特/秒，1字节=8比特）
            download_speed_mbps = (downloaded_mb * 8) / download_duration
            result["download_speed_mbps"] = round(download_speed_mbps, 2)
        else:
            result["download_speed_mbps"] = 0.0
            result["error_msg"] = "未获取到有效流媒体数据（可能是服务器限制或非流媒体链接）"

        return result

    except requests.exceptions.Timeout:
        result["error_msg"] = "请求超时（链接可能失效或网络较差）"
    except requests.exceptions.HTTPError as e:
        result["error_msg"] = f"HTTP错误：{str(e)}"
    except Exception as e:
        result["error_msg"] = f"未知错误：{str(e)}"

    return result

# ===================== 核心函数：批量IPTV链接测速 =====================
def batch_test_iptv_speed(input_links: List[str]) -> List[Dict]:
    """
    批量测试IPTV链接速度，返回排序后的测速结果列表
    :param input_links: 输入的原始链接列表
    :return: 按下载速度降序排序的测速结果列表
    """
    # 第一步：处理输入链接，提取待测速的流媒体链接
    iptv_links = get_iptv_links_from_input(input_links)
    if not iptv_links:
        print("❌  无有效待测速链接，终止测速")
        return []

    # 第二步：批量测速
    speed_results = []
    print("🚀  开始批量测速（按下载速度从快到慢排序，耐心等待...）\n")

    for link in tqdm(iptv_links, desc="测速进度"):
        result = test_single_iptv_speed(link)
        if result:
            speed_results.append(result)

    # 第三步：排序（先按可用状态，再按下载速度降序，最后按延迟升序）
    speed_results.sort(
        key=lambda x: (x["is_available"], x["download_speed_mbps"], -x["response_delay_ms"]),
        reverse=True
    )

    return speed_results

# ===================== 工具函数：打印并保存测速结果 =====================
def print_and_save_results(speed_results: List[Dict]):
    """
    打印测速结果，并按需保存到本地文件
    :param speed_results: 测速结果列表
    """
    if not speed_results:
        print("❌  无测速结果可展示")
        return

    # 整理打印内容
    print("\n" + "="*100)
    print("📊  IPTV测速结果汇总（按下载速度从快到慢排序）")
    print("="*100)
    print(f"{'序号':<4} {'可用状态':<8} {'延迟(ms)':<10} {'下载速度(Mbps)':<15} {'链接简要信息'}")
    print("-"*100)

    save_content = []
    save_content.append("IPTV测速结果汇总（按下载速度从快到慢排序）")
    save_content.append(f"测速时间：{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}")
    save_content.append(f"测速配置：下载测试大小={DOWNLOAD_TEST_SIZE/(1024*1024)}MB，超时时间={TIMEOUT}秒")
    save_content.append("="*100)
    save_content.append(f"{'序号':<4} {'可用状态':<8} {'延迟(ms)':<10} {'下载速度(Mbps)':<15} {'完整链接'} {'错误信息（如有）'}")
    save_content.append("-"*100)

    for idx, result in enumerate(speed_results, 1):
        available_status = "✅ 可用" if result["is_available"] else "❌ 不可用"
        delay = result["response_delay_ms"]
        download_speed = result["download_speed_mbps"]
        link = result["link"]
        error_msg = result["error_msg"]
        link_brief = link[:50] + "..." if len(link) > 50 else link  # 打印时简化长链接

        # 打印到控制台
        print(f"{idx:<4} {available_status:<8} {delay:<10} {download_speed:<15} {link_brief}")

        # 写入保存内容（包含错误信息，方便排查）
        save_line = f"{idx:<4} {available_status:<8} {delay:<10} {download_speed:<15} {link} | 错误信息：{error_msg}"
        save_content.append(save_line)

    # 保存结果到本地文件
    if SAVE_RESULT:
        try:
            with open(RESULT_SAVE_PATH, "w", encoding="utf-8") as f:
                f.write("\n".join(save_content))
            print(f"\n🎉  测速结果已保存到：{os.path.abspath(RESULT_SAVE_PATH)}")
        except Exception as e:
            print(f"\n❌  保存测速结果失败，错误：{str(e)}")

# ===================== 主程序入口（已配置 movie.txt 链接） =====================
if __name__ == "__main__":
    # 优化：直接配置 movie.txt 的 RAW 链接，自动解析其中的流媒体链接
    INPUT_IPTV_LINKS = [
        "https://raw.githubusercontent.com/Lei9008/IPTV/main/input/source/movie.txt"
    ]

    # 步骤1：批量测速
    test_results = batch_test_iptv_speed(INPUT_IPTV_LINKS)

    # 步骤2：打印并保存结果
    print_and_save_results(test_results)
