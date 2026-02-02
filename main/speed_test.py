import requests
import time
import os
from typing import List, Dict, Optional

# 可选：导入tqdm实现进度条（未安装可注释掉，不影响核心功能）
try:
    from tqdm import tqdm
except ImportError:
    tqdm = lambda x, desc=None: x  # 兼容未安装tqdm的情况，定义空实现

# ===================== 配置项（可按需调整） =====================
# 测速参数
DOWNLOAD_TEST_SIZE = 1024 * 1024  # 测速下载数据大小（1MB，可调整，越大越精准但耗时越长）
TIMEOUT = 15  # 网络请求超时时间（秒）
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# 结果保存配置
SAVE_RESULT = True
RESULT_SAVE_PATH = "iptv_speed_test_result.txt"

# ===================== 工具函数：解析m3u文件（提取IPTV流媒体链接） =====================
def parse_m3u_content(m3u_content: str) -> List[str]:
    """
    解析m3u格式内容，提取有效的IPTV流媒体链接
    :param m3u_content: m3u文本内容
    :return: 提取到的流媒体链接列表
    """
    iptv_links = []
    lines = m3u_content.split("\n")
    for line in lines:
        line = line.strip()
        # 过滤注释行和空行，提取http/https开头的流媒体链接
        if line and not line.startswith("#") and (line.startswith("http://") or line.startswith("https://")):
            iptv_links.append(line)
    return iptv_links

def get_iptv_links_from_input(input_links: List[str]) -> List[str]:
    """
    处理输入链接列表，自动解析m3u链接，返回最终待测速的流媒体链接列表
    :param input_links: 输入的原始链接列表（包含普通流媒体链接和m3u链接）
    :return: 待测速的纯流媒体链接列表
    """
    final_links = []
    headers = {"User-Agent": USER_AGENT}

    for link in input_links:
        link = link.strip()
        if not link:
            continue

        # 判断是否为m3u链接（后缀为.m3u或.m3u8）
        if link.endswith(".m3u") or link.endswith(".m3u8"):
            try:
                response = requests.get(link, headers=headers, timeout=TIMEOUT)
                response.raise_for_status()
                m3u_links = parse_m3u_content(response.text)
                final_links.extend(m3u_links)
                print(f"✅  解析m3u链接成功，提取到 {len(m3u_links)} 个流媒体链接：{link}")
            except Exception as e:
                print(f"❌  解析m3u链接失败，跳过：{link}，错误：{str(e)}")
        else:
            # 普通流媒体链接，直接加入列表
            final_links.append(link)

    # 去重，避免重复测速
    final_unique_links = list(dict.fromkeys(final_links))
    print(f"\n🎉  链接处理完成，共获取 {len(final_unique_links)} 个唯一待测速IPTV链接\n")
    return final_unique_links

# ===================== 核心函数：单个IPTV链接测速 =====================
def test_single_iptv_speed(link: str) -> Optional[Dict]:
    """
    测试单个IPTV链接的速度，返回测速结果（包含连通性、延迟、下载速度）
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
        # 发送HEAD请求（优先，获取头信息更高效，部分服务器不支持则降级为GET）
        try:
            response = requests.head(link, headers=headers, timeout=TIMEOUT, stream=True)
        except:
            response = requests.get(link, headers=headers, timeout=TIMEOUT, stream=True)
        response.raise_for_status()
        end_time = time.time()

        response_delay = (end_time - start_time) * 1000  # 转为毫秒
        result["response_delay_ms"] = round(response_delay, 2)
        result["is_available"] = True

        # 2. 测试下载速度（拉取指定大小的数据流）
        downloaded_size = 0
        download_start_time = time.time()

        for chunk in response.iter_content(chunk_size=1024):
            if chunk:
                downloaded_size += len(chunk)
                # 达到测试大小或超时则停止
                if downloaded_size >= DOWNLOAD_TEST_SIZE or (time.time() - download_start_time) > TIMEOUT:
                    break

        download_end_time = time.time()
        download_duration = download_end_time - download_start_time

        # 计算下载速度（Mbps：兆比特/秒，1字节=8比特）
        if download_duration > 0 and downloaded_size > 0:
            # 转为MB（字节）
            downloaded_mb = downloaded_size / (1024 * 1024)
            # 转为Mbps
            download_speed_mbps = (downloaded_mb * 8) / download_duration
            result["download_speed_mbps"] = round(download_speed_mbps, 2)

        return result

    except requests.exceptions.Timeout:
        result["error_msg"] = "请求超时"
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

    # 第三步：排序（先按可用状态，再按下载速度降序）
    speed_results.sort(
        key=lambda x: (x["is_available"], x["download_speed_mbps"]),
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
    save_content.append(f"{'序号':<4} {'可用状态':<8} {'延迟(ms)':<10} {'下载速度(Mbps)':<15} {'完整链接'}")
    save_content.append("-"*100)

    for idx, result in enumerate(speed_results, 1):
        available_status = "✅ 可用" if result["is_available"] else "❌ 不可用"
        delay = result["response_delay_ms"]
        download_speed = result["download_speed_mbps"]
        link = result["link"]
        link_brief = link[:50] + "..." if len(link) > 50 else link  # 打印时简化长链接

        # 打印到控制台
        print(f"{idx:<4} {available_status:<8} {delay:<10} {download_speed:<15} {link_brief}")

        # 写入保存内容
        save_line = f"{idx:<4} {available_status:<8} {delay:<10} {download_speed:<15} {link}"
        save_content.append(save_line)

    # 保存结果到本地文件
    if SAVE_RESULT:
        try:
            with open(RESULT_SAVE_PATH, "w", encoding="utf-8") as f:
                f.write("\n".join(save_content))
            print(f"\n🎉  测速结果已保存到：{os.path.abspath(RESULT_SAVE_PATH)}")
        except Exception as e:
            print(f"\n❌  保存测速结果失败，错误：{str(e)}")

# ===================== 主程序入口 =====================
if __name__ == "__main__":
    # 示例：待测速的IPTV链接列表（可替换为你自己的链接，支持m3u/m3u8和普通流媒体链接）
    INPUT_IPTV_LINKS = [
        # 替换为你的IPTV链接
         "https://raw.githubusercontent.com/Lei9008/IPTV/main/input/source/movie.txt"

      
    ]

    # 步骤1：批量测速
    test_results = batch_test_iptv_speed(INPUT_IPTV_LINKS)

    # 步骤2：打印并保存结果
    print_and_save_results(test_results)
