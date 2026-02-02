import re
import requests
import logging
import asyncio
import aiohttp
import time
import os
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
    "CONCURRENT_LIMIT": 20,    # 并发测速数
    "TIMEOUT": 10,             # 单个请求超时（s）
    "RETRY_TIMES": 2,          # 单个URL重试次数
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
LOG_FILE_PATH = OUTPUT_FOLDER / "iptv_core.log"
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

# ===================== 数据结构（核心所需，极简） =====================
@dataclass
class SpeedTestResult:
    """测速结果数据类（仅保留核心字段）"""
    url: str
    latency: Optional[float] = None  # 延迟（ms）
    success: bool = False            # 是否访问成功
    error: Optional[str] = None      # 失败原因

@dataclass
class ChannelInfo:
    """频道基础信息（仅保留核心标识）"""
    url: str
    channel_name: str
    source_url: str  # 来源直播源URL

# 全局缓存（核心流程所需）
channel_cache: List[ChannelInfo] = []  # 存储提取的所有频道
speed_test_results: Dict[str, SpeedTestResult] = {}  # 测速结果映射

# ===================== 模块1：抓取配置源（轻量化） =====================
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

def extract_channels_from_content(content: str, source_url: str) -> List[ChannelInfo]:
    """从源内容中提取频道（仅匹配HTTP/HTTPS URL，极简解析）"""
    channels = []
    # 匹配所有播放URL（仅支持http/https）
    url_pattern = r'(https?://[^\s#\n\r,|]+)'
    url_matches = re.findall(url_pattern, content, re.IGNORECASE | re.MULTILINE)
    
    seen_urls = set()  # 去重
    for url in url_matches:
        url = url.strip()
        if not url or url in seen_urls:
            continue
        
        # 简单提取频道名（从URL中截取）
        channel_name = "未知频道"
        url_parts = url.split('/')
        for part in url_parts:
            if part and len(part) > 3 and not part.startswith(('http', 'www', 'live', 'cdn', 'stream')):
                channel_name = part
                break
        
        seen_urls.add(url)
        channels.append(ChannelInfo(
            url=url,
            channel_name=channel_name,
            source_url=source_url
        ))
    
    logger.info(f"从源 {source_url} 提取到 {len(channels)} 个有效频道")
    return channels

def fetch_all_config_sources() -> List[ChannelInfo]:
    """抓取所有配置源，汇总频道列表（模块1入口）"""
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
        
        channels = extract_channels_from_content(content, source_url)
        all_channels.extend(channels)
    
    # 全局去重（基于播放URL）
    unique_urls = set()
    unique_channels = []
    for channel in all_channels:
        if channel.url not in unique_urls:
            unique_urls.add(channel.url)
            unique_channels.append(channel)
    
    logger.info(f"配置源抓取完成，去重后共 {len(unique_channels)} 个频道")
    global channel_cache
    channel_cache = unique_channels
    return unique_channels

# ===================== 模块2：收集所有URL（极简） =====================
def collect_all_urls() -> List[str]:
    """从频道缓存中收集所有待测速的URL（模块2入口）"""
    if not channel_cache:
        logger.warning("频道缓存为空，无URL可收集")
        return []
    
    all_urls = [channel.url for channel in channel_cache]
    logger.info(f"成功收集 {len(all_urls)} 个待测速URL")
    return all_urls

# ===================== 模块3：异步批量测速（核心保留，轻量化） =====================
class CoreSpeedTester:
    """核心异步测速器（仅保留批量测速功能）"""
    def __init__(self):
        self.session = None
        self.concurrent_limit = getattr(config, 'CONCURRENT_LIMIT', CONFIG_DEFAULTS["CONCURRENT_LIMIT"])
        self.timeout = getattr(config, 'TIMEOUT', CONFIG_DEFAULTS["TIMEOUT"])
        self.retry_times = getattr(config, 'RETRY_TIMES', CONFIG_DEFAULTS["RETRY_TIMES"])
        self.processed_count = 0
        self.total_count = 0
        self.start_time = None
    
    async def __aenter__(self):
        """创建异步会话"""
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        connector = aiohttp.TCPConnector(limit=self.concurrent_limit)
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        
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
        """更新测速进度（极简）"""
        self.processed_count += 1
        if self.processed_count % 50 == 0 or self.processed_count == self.total_count:
            elapsed = time.time() - self.start_time
            speed = self.processed_count / elapsed if elapsed > 0 else 0
            logger.info(f"测速进度：{self.processed_count}/{self.total_count}（{self.processed_count/self.total_count*100:.1f}%），速度：{speed:.1f} URL/s")
    
    async def measure_single_url(self, url: str) -> SpeedTestResult:
        """测量单个URL的可用性和延迟"""
        result = SpeedTestResult(url=url)
        
        for attempt in range(self.retry_times + 1):
            try:
                start_time = time.time()
                async with self.session.get(url) as response:
                    # 仅判断状态码200为成功
                    if response.status == 200:
                        result.latency = (time.time() - start_time) * 1000
                        result.success = True
                        break
                    else:
                        result.error = f"HTTP状态码：{response.status}"
            except asyncio.TimeoutError:
                result.error = "请求超时"
            except aiohttp.ClientConnectionError:
                result.error = "连接失败"
            except Exception as e:
                result.error = f"未知错误：{str(e)[:30]}"
            
            if attempt < self.retry_times:
                await asyncio.sleep(0.5)
        
        self._update_progress()
        return result
    
    async def batch_test(self, urls: List[str]) -> Dict[str, SpeedTestResult]:
        """批量测速（模块3入口）"""
        results = {}
        self.total_count = len(urls)
        self.processed_count = 0
        self.start_time = time.time()
        
        if self.total_count == 0:
            logger.info("无URL需要测速")
            return results
        
        logger.info(f"开始批量测速：共{self.total_count}个URL，并发数：{self.concurrent_limit}，超时：{self.timeout}s")
        
        # 并发控制
        semaphore = asyncio.Semaphore(self.concurrent_limit)
        
        async def worker(url):
            async with semaphore:
                res = await self.measure_single_url(url)
                results[url] = res
        
        # 创建并执行任务
        tasks = [worker(url) for url in urls if url.strip()]
        await asyncio.gather(*tasks)
        
        # 统计结果
        success_count = sum(1 for r in results.values() if r.success)
        logger.info(f"测速完成：成功{success_count}/{self.total_count}（{success_count/self.total_count*100:.1f}%）")
        
        global speed_test_results
        speed_test_results = results
        return results

# ===================== 模块4：按是否成功筛选（核心极简） =====================
def filter_valid_channels() -> Tuple[List[ChannelInfo], List[ChannelInfo]]:
    """筛选有效频道（成功+延迟达标）和无效频道（模块4入口）"""
    latency_threshold = getattr(config, 'LATENCY_THRESHOLD', CONFIG_DEFAULTS["LATENCY_THRESHOLD"])
    valid_channels = []
    invalid_channels = []
    
    for channel in channel_cache:
        result = speed_test_results.get(channel.url)
        if not result:
            invalid_channels.append(channel)
            continue
        
        # 筛选条件：访问成功 + 延迟≤阈值
        if result.success and (result.latency is not None and result.latency <= latency_threshold):
            valid_channels.append(channel)
        else:
            invalid_channels.append(channel)
    
    logger.info(f"筛选完成：有效频道{len(valid_channels)}个（延迟≤{latency_threshold}ms），无效频道{len(invalid_channels)}个")
    return valid_channels, invalid_channels

# ===================== 模块5：生成纯净文件+测速报告（核心） =====================
def generate_pure_files(valid_channels: List[ChannelInfo]):
    """生成纯净M3U/TXT文件（模块5-1）"""
    # 文件路径
    m3u_path = OUTPUT_FOLDER / "live_valid.m3u"
    txt_path = OUTPUT_FOLDER / "live_valid.txt"
    
    try:
        with open(m3u_path, "w", encoding="utf-8") as f_m3u, \
             open(txt_path, "w", encoding="utf-8") as f_txt:
            
            # M3U文件头部（纯净格式）
            f_m3u.write("#EXTM3U\n")
            
            # 写入有效频道
            for idx, channel in enumerate(valid_channels, 1):
                # M3U格式（极简，可直接导入播放器）
                f_m3u.write(f"#EXTINF:-1,{channel.channel_name}\n")
                f_m3u.write(f"{channel.url}\n")
                
                # TXT格式（频道名,URL）
                f_txt.write(f"{channel.channel_name},{channel.url}\n")
        
        logger.info(f"纯净文件生成完成：")
        logger.info(f"  - M3U文件：{m3u_path}（{len(valid_channels)}个有效频道）")
        logger.info(f"  - TXT文件：{txt_path}")
    except Exception as e:
        logger.error(f"生成纯净文件失败：{str(e)}")

def generate_speed_report(valid_channels: List[ChannelInfo], invalid_channels: List[ChannelInfo]):
    """生成详细测速报告（模块5-2）"""
    report_path = OUTPUT_FOLDER / "speed_report.txt"
    latency_threshold = getattr(config, 'LATENCY_THRESHOLD', CONFIG_DEFAULTS["LATENCY_THRESHOLD"])
    
    try:
        with open(report_path, "w", encoding="utf-8") as f:
            # 报告头部
            f.write("IPTV核心流程测速报告\n")
            f.write("="*80 + "\n")
            f.write(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"延迟阈值：{latency_threshold}ms | 并发数：{config.CONCURRENT_LIMIT}\n")
            f.write(f"总频道数：{len(channel_cache)} | 有效频道数：{len(valid_channels)} | 无效频道数：{len(invalid_channels)}\n")
            f.write(f"有效率：{len(valid_channels)/len(channel_cache)*100:.1f}%\n")
            f.write("="*80 + "\n\n")
            
            # 有效频道列表（按延迟升序）
            if valid_channels:
                f.write("【有效频道列表（按延迟升序）】\n")
                # 按延迟排序
                valid_channels_sorted = sorted(
                    valid_channels,
                    key=lambda c: speed_test_results[c.url].latency or 9999
                )
                f.write(f"{'排名':<4} {'频道名':<20} {'延迟(ms)':<10} {'播放URL'}\n")
                f.write("-"*80 + "\n")
                for idx, channel in enumerate(valid_channels_sorted, 1):
                    latency = speed_test_results[channel.url].latency or 0
                    f.write(f"{idx:<4} {channel.channel_name[:20]:<20} {latency:<10.2f} {channel.url[:50]}...\n")
                f.write("\n")
            
            # 无效频道列表（简要）
            if invalid_channels:
                f.write("【无效频道列表（简要）】\n")
                f.write(f"{'排名':<4} {'频道名':<20} {'失败原因':<20} {'播放URL'}\n")
                f.write("-"*80 + "\n")
                for idx, channel in enumerate(invalid_channels[:50], 1):  # 仅显示前50个
                    result = speed_test_results.get(channel.url)
                    error = result.error if result else "未测速"
                    f.write(f"{idx:<4} {channel.channel_name[:20]:<20} {error[:20]:<20} {channel.url[:50]}...\n")
                if len(invalid_channels) > 50:
                    f.write(f"... 共{len(invalid_channels)}个无效频道，仅显示前50个\n")
        
        logger.info(f"测速报告生成完成：{report_path}")
    except Exception as e:
        logger.error(f"生成测速报告失败：{str(e)}")

def generate_all_output(valid_channels: List[ChannelInfo], invalid_channels: List[ChannelInfo]):
    """生成所有输出文件（模块5入口）"""
    generate_pure_files(valid_channels)
    generate_speed_report(valid_channels, invalid_channels)

# ===================== 核心流程入口（串联5个模块） =====================
async def main():
    """核心流程：抓取配置源 → 收集所有URL → 异步批量测速 → 筛选 → 生成文件+报告"""
    start_total = time.time()
    try:
        # 步骤1：抓取配置源
        logger.info("\n===== 步骤1：抓取配置源 =====")
        fetch_all_config_sources()
        
        # 步骤2：收集所有URL
        logger.info("\n===== 步骤2：收集所有待测速URL =====")
        all_urls = collect_all_urls()
        if not all_urls:
            logger.error("无待测速URL，终止流程")
            return
        
        # 步骤3：异步批量测速
        logger.info("\n===== 步骤3：异步批量测速 =====")
        async with CoreSpeedTester() as tester:
            await tester.batch_test(all_urls)
        
        # 步骤4：筛选有效/无效频道
        logger.info("\n===== 步骤4：筛选有效频道 =====")
        valid_channels, invalid_channels = filter_valid_channels()
        
        # 步骤5：生成纯净文件+测速报告
        logger.info("\n===== 步骤5：生成输出文件 =====")
        generate_all_output(valid_channels, invalid_channels)
        
        # 总耗时统计
        total_elapsed = time.time() - start_total
        logger.info(f"\n===== 核心流程全部完成，总耗时：{total_elapsed:.1f}s =====")
    
    except Exception as e:
        logger.critical(f"核心流程执行异常：{str(e)}", exc_info=True)

# ===================== 运行入口（兼容Windows） =====================
if __name__ == "__main__":
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
