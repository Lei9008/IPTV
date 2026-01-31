import re
import requests
import logging
import warnings
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple, Set, OrderedDict as OrderedDictType
import difflib

# 导入配置文件（确保config.py与当前脚本在同一目录）
import config
import os

# ===================== 基础配置 =====================
warnings.filterwarnings('ignore', category=requests.packages.urllib3.exceptions.InsecureRequestWarning)
OUTPUT_FOLDER = Path("output")
OUTPUT_FOLDER.mkdir(exist_ok=True)

# 支持的GitHub镜像域名
GITHUB_MIRRORS = [
    "raw.githubusercontent.com",
    "raw.kkgithub.com",
    "raw.githubusercontents.com",
    "raw.fgit.cf",
    "raw.fgithub.de"
]

# 支持的GitHub代理前缀
PROXY_PREFIXES = [
    "https://ghproxy.com/",
    "https://mirror.ghproxy.com/",
    "https://gh.api.99988866.xyz/"
]

# 扩展：支持的直播源协议（解决RTSP被过滤的问题）
SUPPORTED_PROTOCOLS = (
    "http://",
    "https://",
    "rtsp://",
    "rtmp://",
    "m3u8://",
    "hls://"
)

LOG_FILE_PATH = OUTPUT_FOLDER / "live_source_extract.log"
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

# ===================== 数据结构 =====================
@dataclass
class ChannelMeta:
    url: str
    raw_extinf: str = ""
    tvg_id: Optional[str] = None
    tvg_name: Optional[str] = None
    tvg_logo: Optional[str] = None
    group_title: Optional[str] = None
    channel_name: Optional[str] = None
    source_url: str = ""
    protocol: str = ""  # 保留协议记录（仅用于内部，不输出到M3U）
    cleaned_channel_name: str = ""  # 新增：清洗后的频道名称（用于模板匹配）

channel_meta_cache: Dict[str, ChannelMeta] = {}
url_source_mapping: Dict[str, str] = {}

# ===================== 模板相关核心功能（移植并优化自第一段代码） =====================
def clean_channel_name(channel_name: Optional[str]) -> str:
    """
    数据清洗函数（移植自第一段代码）
    去除特殊字符、空白，格式化数字，转大写，用于模板匹配
    """
    if not channel_name:
        return ""
    cleaned_name = re.sub(r'[$「」\-]', '', channel_name)  # 去除特殊字符
    cleaned_name = re.sub(r'\s+', '', cleaned_name)  # 去除所有空白字符
    cleaned_name = re.sub(r'(\D*)(\d+)', lambda m: m.group(1) + str(int(m.group(2))), cleaned_name)  # 数字格式化
    return cleaned_name.upper()  # 转大写

def parse_template(template_file: str) -> OrderedDictType[str, List[str]]:
    """
    解析模板文件（移植自第一段代码）
    提取频道分类和频道名称，返回有序字典（分类→[清洗后的频道名称列表]）
    """
    template_channels = OrderedDict()
    current_category = None
    template_path = Path(template_file)
    
    if not template_path.exists():
        logger.error(f"模板文件不存在：{template_path.absolute()}")
        return template_channels
    
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    if "#genre#" in line:
                        # 提取当前分类
                        current_category = line.split(",")[0].strip()
                        if current_category not in template_channels:
                            template_channels[current_category] = []
                    elif current_category:
                        # 提取频道名称并清洗，保证匹配一致性
                        channel_name = line.split(",")[0].strip()
                        cleaned_channel = clean_channel_name(channel_name)
                        if cleaned_channel:
                            template_channels[current_category].append(cleaned_channel)
        logger.info(f"模板文件解析成功：{template_path.absolute()}，提取到 {len(template_channels)} 个分类，{sum(len(v) for v in template_channels.values())} 个频道")
    except Exception as e:
        logger.error(f"模板文件解析失败：{str(e)}", exc_info=True)
    
    return template_channels

def find_similar_name(target_name: str, name_list: List[str], cutoff: float = 0.6) -> Optional[str]:
    """
    查找最相似的名称（移植自第一段代码）
    使用difflib进行字符串相似度匹配，返回最相似的名称
    """
    if not target_name or not name_list:
        return None
    matches = difflib.get_close_matches(target_name, name_list, n=1, cutoff=cutoff)
    return matches[0] if matches else None

def match_channels(template_channels: OrderedDictType[str, List[str]], all_extracted_channels: OrderedDictType[str, List[Tuple[str, str]]]) -> OrderedDictType[str, List[Tuple[str, str]]]:
    """
    匹配模板中的频道与抓取到的频道（移植并优化自第一段代码）
    仅保留模板中存在（或相似度匹配）的频道，返回匹配后的有序字典
    """
    matched_channels = OrderedDict()
    if not template_channels or not all_extracted_channels:
        logger.warning("模板或抓取到的频道为空，无法进行匹配")
        return matched_channels
    
    # 第一步：收集所有抓取到的频道（清洗后名称→(原始名称, URL) 映射）
    extracted_name_url_mapping: Dict[str, List[Tuple[str, str]]] = {}
    all_extracted_cleaned_names: List[str] = []
    
    for _, channel_list in all_extracted_channels.items():
        for original_name, url in channel_list:
            cleaned_name = clean_channel_name(original_name)
            if cleaned_name:
                if cleaned_name not in extracted_name_url_mapping:
                    extracted_name_url_mapping[cleaned_name] = []
                extracted_name_url_mapping[cleaned_name].append((original_name, url))
                all_extracted_cleaned_names.append(cleaned_name)
    
    # 第二步：遍历模板，进行相似度匹配并收集结果
    for template_category, template_channel_list in template_channels.items():
        matched_channel_list = []
        for template_channel in template_channel_list:
            # 查找相似名称
            similar_cleaned_name = find_similar_name(template_channel, all_extracted_cleaned_names)
            if similar_cleaned_name and similar_cleaned_name in extracted_name_url_mapping:
                # 合并匹配到的频道（去重URL）
                seen_urls = set()
                for original_name, url in extracted_name_url_mapping[similar_cleaned_name]:
                    if url not in seen_urls:
                        seen_urls.add(url)
                        matched_channel_list.append((original_name, url))
        
        # 仅保留有有效频道的分类
        if matched_channel_list:
            matched_channels[template_category] = matched_channel_list
    
    logger.info(f"频道匹配完成：提取到 {len(matched_channels)} 个有效分类，{sum(len(v) for v in matched_channels.values())} 个有效频道")
    return matched_channels

def merge_channels(target: OrderedDictType[str, List[Tuple[str, str]]], source: OrderedDictType[str, List[Tuple[str, str]]]):
    """
    合并两个频道字典（移植并优化自第一段代码）
    按分类合并，仅保留唯一URL，避免重复
    """
    # 先收集目标字典中的所有URL（用于去重）
    url_set = set()
    for _, ch_list in target.items():
        for _, url in ch_list:
            url_set.add(url)
    
    # 遍历源字典，合并新频道（去重）
    for category_name, ch_list in source.items():
        if category_name not in target:
            target[category_name] = []
        for name, url in ch_list:
            if url not in url_set:
                target[category_name].append((name, url))
                url_set.add(url)

# ===================== 原有工具函数（优化数据一致性） =====================
def get_url_protocol(url: str) -> str:
    """提取URL的协议类型，返回标准化协议名称（内部使用）"""
    if not url:
        return "未知协议"
    for proto in SUPPORTED_PROTOCOLS:
        if url.lower().startswith(proto.lower()):
            return proto[:-3].upper()  # 去除"://"，转为大写（如HTTP、RTSP）
    return "未知协议"

def clean_group_title(group_title: Optional[str], channel_name: Optional[str] = "") -> str:
    """
    清洗分类名称（集成config中的分类映射标准化，返回有效分类）
    """
    group_title = group_title or ""
    channel_name = channel_name or ""
    
    # 第一步：通过config中的反向映射实现分类标准化（优先匹配）
    if group_title.strip() in config.group_title_reverse_mapping:
        group_title = config.group_title_reverse_mapping[group_title.strip()]
    
    # 第二步：清洗特殊字符，仅保留中文、字母、数字、下划线、括号
    final_title = ''.join(re.findall(r'[\u4e00-\u9fa5a-zA-Z0-9_\(\)]+', group_title.strip())).strip() or "未分类"
    
    # 第三步：限制长度，避免分类名称过长影响播放器显示
    return final_title[:20] if final_title else "未分类"

def global_replace_cctv_name(content: str) -> str:
    """批量替换文本中的CCTV频道名称为标准名称"""
    if not content:
        return content
    all_mappings = {}
    all_mappings.update(config.cntvNamesReverse)
    all_mappings.update(config.cctv_alias)
    
    # 按名称长度降序排序，避免短名称覆盖长名称（如先匹配"CCTV5+"再匹配"CCTV5"）
    sorted_mappings = sorted(all_mappings.items(), key=lambda x: (-len(x[0]), x[0]))
    replaced_content = content
    
    for old_name, new_name in sorted_mappings:
        if old_name in replaced_content:
            replaced_content = replaced_content.replace(old_name, new_name)
    
    return replaced_content

def standardize_cctv_name(channel_name: Optional[str]) -> str:
    """标准化单个CCTV频道名称"""
    if not channel_name:
        return ""
    
    # 精准匹配反向映射和别名
    if channel_name in config.cntvNamesReverse:
        return config.cntvNamesReverse[channel_name]
    if channel_name in config.cctv_alias:
        return config.cctv_alias[channel_name]
    
    # 模糊匹配（包含关系）
    normalized_name = channel_name.strip()
    for raw_name, standard_name in config.cntvNamesReverse.items():
        if raw_name in normalized_name:
            return standard_name
    for alias_name, standard_name in config.cctv_alias.items():
        if alias_name in normalized_name:
            return standard_name
    
    # 无匹配则返回原名称（清洗前后空格）
    return normalized_name

def replace_github_domain(url: str) -> List[str]:
    """生成GitHub URL的多个候选地址（镜像+代理），提升抓取成功率"""
    if not url or "github" not in url.lower():
        return [url]
    
    candidate_urls = [url]
    # 替换GitHub镜像域名
    for mirror in GITHUB_MIRRORS:
        for original in GITHUB_MIRRORS:
            if original in url:
                new_url = url.replace(original, mirror)
                if new_url not in candidate_urls:
                    candidate_urls.append(new_url)
    
    # 添加代理前缀
    proxy_urls = []
    for base_url in candidate_urls:
        for proxy in PROXY_PREFIXES:
            if not base_url.startswith(proxy):
                proxy_url = proxy + base_url
                if proxy_url not in proxy_urls:
                    proxy_urls.append(proxy_url)
    
    # 去重并保留前5个候选地址（避免过多重试耗时）
    unique_urls = list(dict.fromkeys(candidate_urls + proxy_urls))
    return unique_urls[:5]

def fetch_url_with_retry(url: str, timeout: int = 15) -> Optional[str]:
    """带重试机制的URL内容抓取，支持GitHub镜像/代理自动切换"""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    original_url = url
    
    # 转换GitHub blob地址为raw原始文件地址
    if "github.com" in url and "/blob/" in url:
        url = url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
    
    # 获取候选地址列表
    candidate_urls = replace_github_domain(url)
    timeouts = [5, 10, 15, 15, 15]  # 超时时间逐步递增
    
    for idx, candidate in enumerate(candidate_urls):
        current_timeout = timeouts[min(idx, len(timeouts)-1)]
        try:
            response = requests.get(
                candidate,
                headers=headers,
                timeout=current_timeout,
                verify=False,
                allow_redirects=True
            )
            response.raise_for_status()  # 抛出HTTP状态码异常（4xx/5xx）
            response.encoding = response.apparent_encoding or 'utf-8'  # 自动识别编码
            return response.text
        except requests.RequestException as e:
            logger.warning(f"抓取失败 [{idx+1}/{len(candidate_urls)}]: {candidate} | {str(e)[:50]}")
            continue
    
    logger.error(f"所有候选地址均抓取失败：{original_url}")
    return None

def extract_m3u_meta(content: str, source_url: str) -> Tuple[OrderedDictType[str, List[Tuple[str, str]]], List[ChannelMeta]]:
    """解析标准M3U格式内容，提取频道元信息和分类（支持多种直播协议）"""
    # 匹配EXTINF行和后续的直播URL
    m3u_pattern = re.compile(
        r"(#EXTINF:-?\d+.*?)\n\s*([^#\n\r\s].*?)(?=\s|#|$)",
        re.IGNORECASE | re.DOTALL | re.MULTILINE
    )
    # 匹配EXTINF中的属性（如tvg-id、group-title）
    attr_pattern = re.compile(r'(\w+)-(\w+)="([^"]*)"')
    
    categorized_channels = OrderedDict()
    meta_list = []
    seen_urls = set()  # 去重（按URL）
    matches = m3u_pattern.findall(content)
    
    logger.info(f"M3U格式匹配到 {len(matches)} 个候选条目")
    
    for raw_extinf, url in matches:
        url = url.strip()
        raw_extinf = raw_extinf.strip()
        
        # 优化：过滤无效URL（非支持协议、已重复、空URL）
        if not url or not url.startswith(SUPPORTED_PROTOCOLS) or url in seen_urls:
            continue
        seen_urls.add(url)
        url_source_mapping[url] = source_url
        
        # 提取EXTINF中的属性
        tvg_id, tvg_name, tvg_logo, group_title = None, None, None, None
        channel_name = ""
        attr_matches = attr_pattern.findall(raw_extinf)
        
        for attr1, attr2, value in attr_matches:
            full_attr = f"{attr1}-{attr2}"
            if full_attr == "tvg-id":
                tvg_id = value
            elif full_attr == "tvg-name":
                tvg_name = standardize_cctv_name(value)
            elif full_attr == "tvg-logo":
                tvg_logo = value
            elif full_attr == "group-title":
                group_title = value
        
        # 提取频道名称（EXTINF行末尾的,后内容）
        name_match = re.search(r',\s*(.+?)\s*$', raw_extinf)
        if name_match:
            channel_name = standardize_cctv_name(name_match.group(1).strip())
        
        # 清洗分类名称
        group_title = clean_group_title(group_title, channel_name)
        # 清洗频道名称（用于后续模板匹配）
        cleaned_channel_name = clean_channel_name(channel_name)
        
        # 提取协议类型（内部使用，不输出）
        protocol = get_url_protocol(url)
        
        # 封装频道元信息（新增清洗后的频道名称）
        meta = ChannelMeta(
            url=url,
            raw_extinf=raw_extinf,
            tvg_id=tvg_id,
            tvg_name=tvg_name,
            tvg_logo=tvg_logo,
            group_title=group_title,
            channel_name=channel_name,
            source_url=source_url,
            protocol=protocol,
            cleaned_channel_name=cleaned_channel_name
        )
        meta_list.append(meta)
        channel_meta_cache[url] = meta
        
        # 按分类整理频道
        if group_title not in categorized_channels:
            categorized_channels[group_title] = []
        categorized_channels[group_title].append((channel_name, url))
    
    logger.info(f"M3U格式提取有效频道数：{len(meta_list)}（支持协议：{SUPPORTED_PROTOCOLS}）")
    return categorized_channels, meta_list

def extract_channels_from_content(content: str, source_url: str) -> OrderedDictType[str, List[Tuple[str, str]]]:
    """兼容解析M3U格式和自定义文本格式的直播源（支持多种直播协议）"""
    categorized_channels = OrderedDict()
    
    # 优先处理标准M3U格式
    if "#EXTM3U" in content:
        m3u_categorized, _ = extract_m3u_meta(content, source_url)
        categorized_channels = m3u_categorized
    else:
        # 处理自定义文本格式
        lines = content.split('\n')
        current_group = ""
        seen_urls = set()
        
        for line in lines:
            line = line.strip()
            
            # 识别分类行（注释中的分类标记）
            if not line or line.startswith(("//", "#", "/*", "*/")):
                if any(keyword in line.lower() for keyword in ['#分类', '#genre', '分类:', 'genre:', '==', '---']):
                    # 提取分类名称
                    group_match = re.search(r'[：:=](\S+)', line)
                    if group_match:
                        current_group = group_match.group(1).strip()
                    else:
                        current_group = re.sub(r'[#分类:genre:==\-—]', '', line).strip() or ""
                continue
            
            # 匹配"名称,URL"或"名称|URL"格式的行
            pattern = r'([^,|#$]+)[,|#$]\s*(' + '|'.join([p[:-3] for p in SUPPORTED_PROTOCOLS]) + r':\/\/[^\s,|#$]+)'
            matches = re.findall(pattern, line, re.IGNORECASE)
            
            if matches:
                for name, url in matches:
                    name = name.strip()
                    url = url.strip()
                    
                    # 过滤无效URL（已重复、非支持协议）
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)
                    url_source_mapping[url] = source_url
                    
                    # 标准化频道名称和分类
                    standard_name = standardize_cctv_name(name)
                    cleaned_channel_name = clean_channel_name(standard_name)  # 新增：清洗频道名称
                    group_title = clean_group_title(current_group, standard_name)
                    
                    # 提取协议类型（内部使用，不输出）
                    protocol = get_url_protocol(url)
                    
                    # 构造标准EXTINF行
                    raw_extinf = f"#EXTINF:-1 tvg-id=\"\" tvg-name=\"{standard_name}\" tvg-logo=\"\" group-title=\"{group_title}\",{standard_name}"
                    meta = ChannelMeta(
                        url=url,
                        raw_extinf=raw_extinf,
                        tvg_id="",
                        tvg_name=standard_name,
                        tvg_logo="",
                        group_title=group_title,
                        channel_name=standard_name,
                        source_url=source_url,
                        protocol=protocol,
                        cleaned_channel_name=cleaned_channel_name  # 新增：清洗后的频道名称
                    )
                    channel_meta_cache[url] = meta
                    
                    # 按分类整理频道
                    if group_title not in categorized_channels:
                        categorized_channels[group_title] = []
                    categorized_channels[group_title].append((standard_name, url))
        
        valid_channel_count = sum(len(v) for v in categorized_channels.values())
        logger.info(f"自定义文本格式提取有效频道数：{valid_channel_count}（支持协议：{SUPPORTED_PROTOCOLS}）")
    
    # 过滤空分类（无有效频道的分类）
    categorized_channels = OrderedDict([(k, v) for k, v in categorized_channels.items() if v])
    return categorized_channels

# ===================== 生成输出文件（保持原有功能，适配匹配后的频道） =====================
def generate_summary(matched_channels: OrderedDictType[str, List[Tuple[str, str]]]):
    """生成汇总TXT文件和纯净版M3U文件（无协议标注，可直接导入播放器）"""
    if not matched_channels:
        logger.warning("无有效匹配频道可输出，跳过文件生成")
        return
    
    # 定义输出文件路径
    summary_path = OUTPUT_FOLDER / "live_source_summary.txt"
    m3u_path = OUTPUT_FOLDER / "live_source_merged.m3u"
    generate_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    total_channels = sum(len(ch_list) for _, ch_list in matched_channels.items())
    total_categories = len(matched_channels)
    
    try:
        # 生成易读的汇总TXT（可选保留协议标注，方便人工查看）
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write("IPTV直播源汇总（按模板匹配+标准化+多协议支持）\n")
            f.write("="*80 + "\n")
            f.write(f"生成时间：{generate_time}\n")
            f.write(f"总频道数：{total_channels}\n")
            f.write(f"分类数：{total_categories}\n")
            f.write(f"支持协议：{', '.join([p[:-3].upper() for p in SUPPORTED_PROTOCOLS])}\n")
            f.write("="*80 + "\n\n")
            
            # 按分类写入频道详情
            for group_title, channel_list in matched_channels.items():
                f.write(f"【{group_title}】（{len(channel_list)}个频道）\n")
                for idx, (name, url) in enumerate(channel_list, 1):
                    source = url_source_mapping.get(url, "未知来源")
                    protocol = get_url_protocol(url)
                    f.write(f"{idx:>3}. {name:<20} [{protocol}] {url}\n")
                    f.write(f"      来源：{source}\n")
                f.write("\n")
        
        # 生成纯净版M3U文件（无协议标注，优化解析兼容性）
        with open(m3u_path, "w", encoding="utf-8") as f:
            f.write("#EXTM3U x-tvg-url=\"\"\n")
            f.write(f"# IPTV直播源匹配合并文件 | 生成时间：{generate_time}\n")
            f.write(f"# 总频道数：{total_channels} | 总分类数：{total_categories}\n\n")
            
            # 按分类写入M3U内容（无协议标注）
            for group_title, channel_list in matched_channels.items():
                f.write(f"# ===== {group_title}（{len(channel_list)}个频道） =====\n")
                for name, url in channel_list:
                    meta = channel_meta_cache.get(url)
                    
                    if meta and meta.raw_extinf:
                        standard_extinf = meta.raw_extinf
                        # 确保分类名称为标准化后的名称
                        if 'group-title="' in standard_extinf:
                            start_idx = standard_extinf.find('group-title="') + len('group-title="')
                            end_idx = standard_extinf.find('"', start_idx)
                            if end_idx > start_idx:
                                standard_extinf = standard_extinf[:start_idx] + group_title + standard_extinf[end_idx:]
                        # 转义特殊字符，避免播放器解析异常（去除协议标注）
                        if ',' in standard_extinf:
                            extinf_part, old_name = standard_extinf.rsplit(',', 1)
                            safe_name = name.replace('\\', '\\\\').replace('$', '\\$')
                            standard_extinf = extinf_part + ',' + safe_name
                        f.write(standard_extinf + "\n")
                    else:
                        # 无元信息时构造默认EXTINF行（无协议标注）
                        safe_name = name.replace('\\', '\\\\').replace('$', '\\$')
                        f.write(f"#EXTINF:-1 tvg-name=\"{safe_name}\" group-title=\"{group_title}\",{safe_name}\n")
                    f.write(url + "\n\n")
        
        logger.info(f"文件生成完成：")
        logger.info(f"  - 汇总TXT：{summary_path.absolute()}")
        logger.info(f"  - 纯净版M3U：{m3u_path.absolute()}")
        
    except Exception as e:
        logger.error(f"生成输出文件失败：{str(e)}", exc_info=True)

# ===================== 主程序入口（新增模板处理流程） =====================
def main(template_file: str = "demo.txt"):
    try:
        # 初始化全局缓存
        global channel_meta_cache, url_source_mapping
        channel_meta_cache = {}
        url_source_mapping = {}
        
        logger.info("="*60)
        logger.info("开始处理IPTV直播源（模板匹配→提取→标准化→合并→生成）")
        logger.info(f"支持的直播协议：{', '.join([p[:-3].upper() for p in SUPPORTED_PROTOCOLS])}")
        logger.info(f"使用的模板文件：{template_file}")
        logger.info("="*60)
        
        # 步骤1：解析模板文件（新增核心步骤）
        template_channels = parse_template(template_file)
        if not template_channels:
            logger.error("模板解析结果为空，程序终止")
            return
        
        # 步骤2：从配置文件读取源URL列表
        source_urls = getattr(config, 'SOURCE_URLS', [])
        if not source_urls:
            logger.error("配置文件中未设置有效SOURCE_URLS，程序终止")
            return
        logger.info(f"读取到待处理的源URL数：{len(source_urls)}")
        
        # 步骤3：初始化全局频道字典（保留顺序），抓取并合并所有源
        all_extracted_channels = OrderedDict()
        failed_urls = []
        
        # 遍历所有源URL，逐个处理
        for idx, url in enumerate(source_urls, 1):
            logger.info(f"\n===== 处理第 {idx}/{len(source_urls)} 个源：{url} =====")
            # 抓取URL内容
            content = fetch_url_with_retry(url)
            if content is None:
                failed_urls.append(url)
                continue
            # 批量替换CCTV频道名称
            content = global_replace_cctv_name(content)
            # 提取频道信息
            extracted_channels = extract_channels_from_content(content, url)
            # 合并到全局频道字典
            merge_channels(all_extracted_channels, extracted_channels)
        
        # 步骤4：模板与抓取频道的匹配（新增核心步骤）
        matched_channels = match_channels(template_channels, all_extracted_channels)
        
        # 步骤5：输出处理完成统计
        logger.info(f"\n===== 处理完成统计 =====")
        total_extracted_channels = sum(len(ch_list) for _, ch_list in all_extracted_channels.items())
        total_matched_channels = sum(len(ch_list) for _, ch_list in matched_channels.items())
        logger.info(f"  - 源URL总数：{len(source_urls)}")
        logger.info(f"  - 抓取失败源数：{len(failed_urls)}")
        logger.info(f"  - 原始抓取频道数：{total_extracted_channels}")
        logger.info(f"  - 模板匹配后频道数：{total_matched_channels}")
        logger.info(f"  - 模板匹配后分类数：{len(matched_channels)}")
        if matched_channels:
            logger.info(f"  - 匹配后分类列表：{list(matched_channels.keys())}")
        if failed_urls:
            logger.warning(f"  - 失败的源URL列表：{failed_urls}")
        
        # 步骤6：生成输出文件（基于匹配后的频道）
        generate_summary(matched_channels)
        
        logger.info("\n===== 所有操作执行完毕 =====")
        logger.info(f"输出文件存放目录：{OUTPUT_FOLDER.absolute()}")
        
    except Exception as e:
        logger.critical(f"程序运行过程中出现致命异常：{str(e)}", exc_info=True)

if __name__ == "__main__":
    # 可修改模板文件路径（默认同目录下的demo.txt）
    main(template_file="demo.txt")

