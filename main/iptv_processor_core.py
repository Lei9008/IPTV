import re
import requests
import logging
import asyncio
import aiohttp
import time
import os  # 修复导入，兼容系统判断
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple, Set

# ===================== 基础配置（轻量化） =====================
# 屏蔽SSL警告
import warnings
warnings.filterwarnings('ignore', category=requests.packages.urllib3.exceptions.InsecureRequestWarning)

# 目录创建
OUTPUT_FOLDER = Path("output")
OUTPUT_FOLDER.mkdir(exist_ok=True)

# 默认配置（核心流程所需）
CONFIG_DEFAULTS = {
    "LATENCY_THRESHOLD": 500,  # 延迟阈值（ms）
    "CONCURRENT_LIMIT": 20,    # 并发验证数
    "TIMEOUT": 15,             # 单个播放验证超时（s，加长适配播放验证）
    "RETRY_TIMES": 1,          # 单个URL重试次数（播放验证无需多次重试）
    "SOURCE_URLS": [],         # 待抓取的直播源URL
}

# 尝试导入外部配置，无则使用默认值
try:
    import config
except ImportError:
    class config:
        SOURCE_URLS = CONFIG_DEFAULTS["SOURCE_URLS"]
        LATENCY_THRESHOLD = CONFIG_DEFAULTS["LATENCY_THRESHOLD"]
        CONCURRENT_LIMIT = CONFIG_DEFAULTS["CONCURRENT_LIMIT"]
        TIMEOUT = CONFIG_DEFAULTS["TIMEOUT"]
        RETRY_TIMES = CONFIG_DEFAULTS["RETRY_TIMES"]

# 日志配置（仅记录核心流程）
LOG_FILE_PATH = OUTPUT_FOLDER / "iptv_core_v2.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s.%(msecs)03d - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler(LOG_FILE_PATH, "w", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ===================== 数据结构（优化：强化频道名+播放验证） =====================
@dataclass
class PlayTestResult:
    """播放验证结果数据类（替代原测速，强化播放可用性）"""
    url: str
    channel_name: str  # 关联频道名，方便后续生成文档
    latency: Optional[float] = None  # 延迟（ms）
    play_success: bool = False       # 是否成功播放（核心筛选条件）
    error: Optional[str] = None      # 失败原因
    content_length: Optional[str] = None  # 补充：响应内容长度，验证是否为有效媒体流

@dataclass
class ChannelInfo:
    """频道基础信息（优化：精准提取频道名+URL）"""
    url: str
    channel_name: str  # 精准提取的频道名（不再是URL截取）
    source_url: str    # 来源直播源URL

# 全局缓存（核心流程所需）
channel_cache: List[ChannelInfo] = []  # 存储提取的所有频道（带精准名字）
play_test_results: Dict[str, PlayTestResult] = {}  # 播放验证结果映射

# ===================== 模块1：抓取URL源 + 提取名字和各自的URL（核心优化） =====================
def fetch_source_content(url: str) -> Optional[str]:
    """抓取单个配置源的内容（带简单重试）"""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    retry_times = 2  # 抓取重试次数（极简）
    
    for attempt in range(retry_times + 1):
        try:
            response = requests.get(
                url,
                headers=headers,
                timeout=15,
                verify=False,
                allow_redirects=True
            )
            response.raise_for_status()
            response.encoding = response.apparent_encoding or 'utf-8'
            logger.info(f"成功抓取配置源：{url}（尝试{attempt+1}/{retry_times+1}）")
            return response.text
        except Exception as e:
            logger.warning(f"抓取配置源失败：{url}（尝试{attempt+1}/{retry_times+1}），原因：{str(e)[:50]}")
            if attempt < retry_times:
                time.sleep(0.5)
                continue
    
    return None

def extract_channel_name_and_url(content: str, source_url: str) -> List[ChannelInfo]:
    """
    优化：精准提取频道名和对应URL（支持2种主流格式，提升名字准确性）
    格式1：#EXTINF:-1,频道名 → 下一行是URL（标准M3U格式）
    格式2：频道名,URL / 频道名|URL（自定义文本格式）
    """
    channels = []
    content_lines = [line.strip() for line in content.split('\n') if line.strip()]
    seen_urls = set()  # 去重
    
    # 处理格式1：标准M3U格式（优先，最精准）
    m3u_channel_name = None
    for line in content_lines:
        # 匹配M3U频道名行
        if line.startswith("#EXTINF:"):
            # 提取 #EXTINF:-1, 后面的频道名
            m3u_channel_match = re.search(r'#EXTINF:.+,(.+)', line)
            if m3u_channel_match:
                m3u_channel_name = m3u_channel_match.group(1).strip()
            continue
        # 下一行是URL，关联上一步提取的频道名
        elif re.match(r'https?://', line, re.IGNORECASE) and m3u_channel_name:
            url = line.strip()
            if url not in seen_urls:
                seen_urls.add(url)
                channels.append(ChannelInfo(
                    url=url,
                    channel_name=m3u_channel_name,
                    source_url=source_url
                ))
                logger.debug(f"从M3U格式提取：{m3u_channel_name} → {url[:50]}...")
            # 重置频道名，准备提取下一个
            m3u_channel_name = None
    
    # 处理格式2：自定义文本格式（频道名,URL / 频道名|URL）
    custom_pattern = r'(.+?)[,|](https?://[^\s#]+)'
    custom_matches = re.findall(custom_pattern, content, re.IGNORECASE | re.MULTILINE)
    for name, url in custom_matches:
        name = name.strip()
        url = url.strip()
        if not url or url in seen_urls:
            continue
        # 若M3U格式已提取过，跳过（避免重复）
        if any(channel.url == url for channel in channels):
            continue
        seen_urls.add(url)
        # 补充：若名字为空，赋予默认名称
        channel_name = name if name else f"自定义频道_{len(channels)+1}"
        channels.append(ChannelInfo(
            url=url,
            channel_name=channel_name,
            source_url=source_url
        ))
        logger.debug(f"从自定义格式提取：{channel_name} → {url[:50]}...")
    
    # 兜底：提取剩余独立URL（若未被上述格式匹配，保留URL截取名字）
    url_pattern = r'(https?://[^\s#\n\r,|]+)'
    standalone_urls = re.findall(url_pattern, content, re.IGNORECASE | re.MULTILINE)
    for url in standalone_urls:
        url = url.strip()
        if url in seen_urls or any(channel.url == url for channel in channels):
            continue
        seen_urls.add(url)
        # URL截取名字（兜底方案）
        fallback_name = "未知频道"
        url_parts = url.split('/')
        for part in url_parts:
            if part and len(part) > 3 and not part.startswith(('http', 'www', 'live', 'cdn', 'stream')):
                fallback_name = part
                break
        channels.append(ChannelInfo(
            url=url,
            channel_name=fallback_name,
            source_url=source_url
        ))
    
    logger.info(f"从源 {source_url} 提取到 {len(channels)} 个有效频道（带精准名字）")
    return channels

def fetch_and_extract_all_channels() -> List[ChannelInfo]:
    """抓取所有配置源，提取并汇总频道（模块1入口）"""
    all_channels = []
    source_urls = getattr(config, 'SOURCE_URLS', [])
    
    if not source_urls:
        logger.error("未配置任何配置源（SOURCE_URLS），终止抓取")
        return all_channels
    
    logger.info(f"开始抓取配置源，共 {len(source_urls)} 个源")
    for source_url in source_urls:
        content = fetch_source_content(source_url)
        if not content:
            continue
        
        channels = extract_channel_name_and_url(content, source_url)
        all_channels.extend(channels)
    
    # 全局去重（基于播放URL，保留第一个提取的名字）
    unique_urls = set()
    unique_channels = []
    for channel in all_channels:
        if channel.url not in unique_urls:
            unique_urls.add(channel.url)
            unique_channels.append(channel)
    
    logger.info(f"配置源抓取+提取完成，去重后共 {len(unique_channels)} 个频道（均带精准名字）")
    global channel_cache
    channel_cache = unique_channels
    return unique_channels

# ===================== 模块2：收集所有URL（极简，关联频道名） =====================
def collect_all_urls() -> List[str]:
    """从频道缓存中收集所有待验证播放的URL（模块2入口）"""
    if not channel_cache:
        logger.warning("频道缓存为空，无URL可收集")
        return []
    
    all_urls = [channel.url for channel in channel_cache]
    logger.info(f"成功收集 {len(all_urls)} 个待播放验证的URL")
    return all_urls

# ===================== 模块3：异步批量播放验证（核心升级：测速→播放验证） =====================
class CorePlayTester:
    """核心异步播放验证器（验证是否可正常播放，而非仅访问）"""
    def __init__(self):
        self.session = None
        self.concurrent_limit = getattr(config, 'CONCURRENT_LIMIT', CONFIG_DEFAULTS["CONCURRENT_LIMIT"])
        self.timeout = getattr(config, 'TIMEOUT', CONFIG_DEFAULTS["TIMEOUT"])
        self.retry_times = getattr(config, 'RETRY_TIMES', CONFIG_DEFAULTS["RETRY_TIMES"])
        self.processed_count = 0
        self.total_count = 0
        self.start_time = None
    
    async def __aenter__(self):
        """创建异步会话（配置媒体流兼容）"""
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        connector = aiohttp.TCPConnector(limit=self.concurrent_limit)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "video/*, audio/*, */*"  # 声明支持媒体流，提升验证准确性
        }
        
        self.session = aiohttp.ClientSession(
            timeout=timeout,
            headers=headers,
            connector=connector
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """关闭异步会话"""
        if self.session:
            await self.session.close()
    
    def _update_progress(self):
        """更新播放验证进度"""
        self.processed_count += 1
        if self.processed_count % 50 == 0 or self.processed_count == self.total_count:
            elapsed = time.time() - self.start_time
            speed = self.processed_count / elapsed if elapsed > 0 else 0
            logger.info(f"验证进度：{self.processed_count}/{self.total_count}（{self.processed_count/self.total_count*100:.1f}%），速度：{speed:.1f} URL/s")
    
    async def verify_single_play(self, channel: ChannelInfo) -> PlayTestResult:
        """验证单个频道是否可正常播放（核心升级）"""
        result = PlayTestResult(
            url=channel.url,
            channel_name=channel.channel_name
        )
        
        for attempt in range(self.retry_times + 1):
            try:
                start_time = time.time()
                async with self.session.get(channel.url, allow_redirects=True) as response:
                    # 播放验证核心条件（3个）
                    # 1. 状态码200
                    # 2. 响应头包含媒体类型（video/audio）或有有效内容长度
                    # 3. 能读取部分响应内容（验证不是空响应）
                    if response.status == 200:
                        # 提取响应头信息
                        content_type = response.headers.get("Content-Type", "").lower()
                        content_length = response.headers.get("Content-Length", "未知")
                        result.content_length = content_length
                        
                        # 验证媒体类型或有效内容
                        is_media = "video/" in content_type or "audio/" in content_type
                        has_valid_content = content_length != "0" and content_length != "未知"
                        
                        if is_media or has_valid_content:
                            # 读取前1024字节，验证可正常获取内容
                            await response.content.read(1024)
                            
                            # 计算延迟
                            result.latency = (time.time() - start_time) * 1000
                            result.play_success = True
                            break
                        else:
                            result.error = "非媒体流响应，无法播放"
                    else:
                        result.error = f"HTTP状态码：{response.status}"
            except asyncio.TimeoutError:
                result.error = "播放请求超时（无有效响应）"
            except aiohttp.ClientConnectionError:
                result.error = "无法建立连接，播放失败"
            except Exception as e:
                result.error = f"播放验证异常：{str(e)[:30]}"
            
            if attempt < self.retry_times:
                await asyncio.sleep(0.5)
        
        self._update_progress()
        return result
    
    async def batch_verify_play(self, channels: List[ChannelInfo]) -> Dict[str, PlayTestResult]:
        """批量播放验证（模块3入口）"""
        results = {}
        self.total_count = len(channels)
        self.processed_count = 0
        self.start_time = time.time()
        
        if self.total_count == 0:
            logger.info("无频道需要进行播放验证")
            return results
        
        logger.info(f"开始批量播放验证：共{self.total_count}个频道，并发数：{self.concurrent_limit}，超时：{self.timeout}s")
        
        # 并发控制
        semaphore = asyncio.Semaphore(self.concurrent_limit)
        
        async def worker(channel):
            async with semaphore:
                res = await self.verify_single_play(channel)
                results[channel.url] = res
        
        # 创建并执行任务（直接传入频道，关联名字）
        tasks = [worker(channel) for channel in channels]
        await asyncio.gather(*tasks)
        
        # 统计结果
        success_count = sum(1 for r in results.values() if r.play_success)
        logger.info(f"播放验证完成：成功播放{success_count}/{self.total_count}（{success_count/self.total_count*100:.1f}%）")
        
        global play_test_results
        play_test_results = results
        return results

# ===================== 模块4：按是否成功播放筛选（核心优化） =====================
def filter_playable_channels() -> Tuple[List[PlayTestResult], List[PlayTestResult]]:
    """筛选可播放频道（成功播放+延迟达标）和不可播放频道（模块4入口）"""
    latency_threshold = getattr(config, 'LATENCY_THRESHOLD', CONFIG_DEFAULTS["LATENCY_THRESHOLD"])
    playable_results = []
    unplayable_results = []
    
    for result in play_test_results.values():
        # 筛选条件：播放成功 + 延迟≤阈值（延迟为空视为达标）
        if result.play_success and (result.latency is None or result.latency <= latency_threshold):
            playable_results.append(result)
        else:
            unplayable_results.append(result)
    
    logger.info(f"筛选完成：可播放频道{len(playable_results)}个（延迟≤{latency_threshold}ms），不可播放频道{len(unplayable_results)}个")
    return playable_results, unplayable_results

# ===================== 模块5：生成名字+URL的TXT文档+测速（播放）报告 =====================
def generate_name_url_txt(playable_results: List[PlayTestResult]):
    """生成纯净版「名字+URL」TXT文档（模块5-1，核心需求）"""
    txt_path = OUTPUT_FOLDER / "live_playable_name_url.txt"
    
    try:
        # 按频道名排序，便于查找
        playable_results_sorted = sorted(
            playable_results,
            key=lambda r: r.channel_name
        )
        
        with open(txt_path, "w", encoding="utf-8") as f:
            # 文档头部说明
            f.write("IPTV 可播放频道列表（频道名 + 播放URL）\n")
            f.write("="*80 + "\n")
            f.write(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"可播放频道总数：{len(playable_results_sorted)}\n")
            f.write("="*80 + "\n\n")
            
            # 写入核心内容：名字 + URL（每行一条，格式清晰）
            for idx, result in enumerate(playable_results_sorted, 1):
                f.write(f"{idx}. {result.channel_name}\t{result.url}\n")
                # 可选：换行分隔，更易复制
                # f.write(f"{result.channel_name}\n{result.url}\n\n")
        
        logger.info(f"「名字+URL」TXT文档生成完成：{txt_path}（{len(playable_results)}个可播放频道）")
    except Exception as e:
        logger.error(f"生成「名字+URL」TXT文档失败：{str(e)}")

def generate_play_report(playable_results: List[PlayTestResult], unplayable_results: List[PlayTestResult]):
    """生成详细播放验证报告（模块5-2，替代原测速报告）"""
    report_path = OUTPUT_FOLDER / "play_verify_report.txt"
    latency_threshold = getattr(config, 'LATENCY_THRESHOLD', CONFIG_DEFAULTS["LATENCY_THRESHOLD"])
    
    try:
        with open(report_path, "w", encoding="utf-8") as f:
            # 报告头部
            f.write("IPTV 播放验证详细报告\n")
            f.write("="*80 + "\n")
            f.write(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"延迟阈值：{latency_threshold}ms | 并发验证数：{config.CONCURRENT_LIMIT}\n")
            f.write(f"总频道数：{len(play_test_results)} | 可播放频道数：{len(playable_results)} | 不可播放频道数：{len(unplayable_results)}\n")
            f.write(f"可播放率：{len(playable_results)/len(play_test_results)*100:.1f}%\n")
            f.write("="*80 + "\n\n")
            
            # 可播放频道列表（按延迟升序，带详细信息）
            if playable_results:
                f.write("【可播放频道列表（按延迟升序）】\n")
                playable_sorted = sorted(
                    playable_results,
                    key=lambda r: r.latency or 9999
                )
                f.write(f"{'排名':<4} {'频道名':<25} {'延迟(ms)':<10} {'内容长度':<15} {'播放URL'}\n")
                f.write("-"*80 + "\n")
                for idx, result in enumerate(playable_sorted, 1):
                    latency = result.latency or 0.0
                    content_len = result.content_length or "未知"
                    f.write(f"{idx:<4} {result.channel_name[:25]:<25} {latency:<10.2f} {content_len[:15]:<15} {result.url[:50]}...\n")
                f.write("\n")
            
            # 不可播放频道列表（简要）
            if unplayable_results:
                f.write("【不可播放频道列表（简要）】\n")
                f.write(f"{'排名':<4} {'频道名':<25} {'失败原因':<20} {'播放URL'}\n")
                f.write("-"*80 + "\n")
                for idx, result in enumerate(unplayable_results[:50], 1):  # 仅显示前50个，避免报告过大
                    error = result.error or "未知原因"
                    f.write(f"{idx:<4} {result.channel_name[:25]:<25} {error[:20]:<20} {result.url[:50]}...\n")
                if len(unplayable_results) > 50:
                    f.write(f"... 共{len(unplayable_results)}个不可播放频道，仅显示前50个\n")
        
        logger.info(f"播放验证报告生成完成：{report_path}")
    except Exception as e:
        logger.error(f"生成播放验证报告失败：{str(e)}")

def generate_all_output(playable_results: List[PlayTestResult], unplayable_results: List[PlayTestResult]):
    """生成所有输出文件（模块5入口）"""
    generate_name_url_txt(playable_results)
    generate_play_report(playable_results, unplayable_results)

# ===================== 核心流程入口（串联5个模块，贴合新需求） =====================
async def main():
    """核心流程：抓取URL源 → 提取名字+URL → 收集所有URL → 异步批量播放验证 → 筛选 → 生成TXT+报告"""
    start_total = time.time()
    try:
        # 步骤1：抓取URL源 + 提取名字和各自的URL
        logger.info("\n===== 步骤1：抓取URL源 + 提取频道名+URL =====")
        fetch_and_extract_all_channels()
        
        # 步骤2：收集所有URL
        logger.info("\n===== 步骤2：收集所有待播放验证的URL =====")
        all_urls = collect_all_urls()
        if not all_urls or not channel_cache:
            logger.error("无待播放验证的频道，终止流程")
            return
        
        # 步骤3：异步批量播放验证
        logger.info("\n===== 步骤3：异步批量播放验证 =====")
        async with CorePlayTester() as tester:
            await tester.batch_verify_play(channel_cache)
        
        # 步骤4：按是否成功播放筛选
        logger.info("\n===== 步骤4：筛选可播放频道 =====")
        playable_results, unplayable_results = filter_playable_channels()
        
        # 步骤5：生成名字+URL的TXT文档+播放报告
        logger.info("\n===== 步骤5：生成输出文件 =====")
        generate_all_output(playable_results, unplayable_results)
        
        # 总耗时统计
        total_elapsed = time.time() - start_total
        logger.info(f"\n===== 核心流程全部完成，总耗时：{total_elapsed:.1f}s =====")
    
    except Exception as e:
        logger.critical(f"核心流程执行异常：{str(e)}", exc_info=True)

# ===================== 运行入口（兼容Windows/Linux） =====================
if __name__ == "__main__":
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
