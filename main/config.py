# config.py
# ===================== 直播源配置（核心） =====================
# 源URL列表（已优化格式，提升抓取成功率）
SOURCE_URLS = [
    # 修正：GitHub blob地址 → raw原始文件地址，移除无效代理前缀格式
    "https://raw.githubusercontent.com/Lei9008/iptv_api_1/main/output/live_ipv4.m3u",
    "https://ghfast.top/raw.githubusercontent.com/plsy1/iptv/main/unicast/unicast-ku9.m3u",
    "https://ghfast.top/raw.githubusercontent.com/plsy1/iptv/main/multicast/multicast-jining.m3u",
    "https://raw.githubusercontent.com/plsy1/iqilu/main/iqilu-generic.m3u",
    "https://raw.githubusercontent.com/develop202/migu_video/main/interface.txt",
]

# ========== 模板相关配置（已实现生效逻辑） ==========
#USE_TEMPLATE = True  # 启用模板匹配
#TEMPLATE_FILE = "demo.txt"  # 模板文件名称，与脚本同目录

# 基础频道名称映射
cntvNamesReverse = {
    # 基础频道
    "CCTV1综合": "CCTV1",
    "CCTV2财经": "CCTV2",
    "CCTV3综艺": "CCTV3",
    "CCTV4中文国际": "CCTV4",
    "CCTV5体育": "CCTV5",
    "CCTV5+体育赛事": "CCTV5+",
    "CCTV6电影": "CCTV6",
    "CCTV7国防军事": "CCTV7",
    "CCTV8电视剧": "CCTV8",
    "CCTV9纪录": "CCTV9",
    "CCTV10科教": "CCTV10",
    "CCTV11戏曲": "CCTV11",
    "CCTV12社会与法": "CCTV12",
    "CCTV13新闻": "CCTV13",
    "CCTV14少儿": "CCTV14",
    "CCTV15音乐": "CCTV15",
    "CCTV16奥林匹克": "CCTV16",
    "CCTV17农业农村": "CCTV17",
    # 海外频道
    "CCTV4中文国际(欧洲)": "CCTV4欧洲",
    "CCTV4中文国际(美洲)": "CCTV4美洲",
}

# 非规范名称的别名映射（增强模糊匹配）
cctv_alias = {
    "央视1套": "CCTV1",
    "中央1套": "CCTV1",
    "央视2套": "CCTV2",
    "中央2套": "CCTV2",
    "央视3套": "CCTV3",
    "中央3套": "CCTV3",
    "央视4套": "CCTV4",
    "中央4套": "CCTV4",
    "央视5套": "CCTV5",
    "中央5套": "CCTV5",
    "央视5+套": "CCTV5+",
    "中央5+套": "CCTV5+",
    "央视6套": "CCTV6",
    "中央6套": "CCTV6",
    "央视7套": "CCTV7",
    "中央7套": "CCTV7",
    "央视8套": "CCTV8",
    "中央8套": "CCTV8",
    "央视9套": "CCTV9",
    "中央9套": "CCTV9",
    "央视10套": "CCTV10",
    "中央10套": "CCTV10",
    "央视11套": "CCTV11",
    "中央11套": "CCTV11",
    "央视12套": "CCTV12",
    "中央12套": "CCTV12",
    "央视13套": "CCTV13",
    "中央13套": "CCTV13",
    "央视14套": "CCTV14",
    "中央14套": "CCTV14",
    "央视15套": "CCTV15",
    "中央15套": "CCTV15",
    "央视16套": "CCTV16",
    "中央16套": "CCTV16",
    "央视17套": "CCTV17",
    "中央17套": "CCTV17",
    "CCTV9纪录片": "CCTV9",
}

# 修正后的 group-title 标准化映射（解决重复键问题，多对一）
# 格式：{目标名称: [需要映射的原始名称列表]}
group_title_mapping = {
    # 地区频道
    '安徽频道': ['安徽地区'],
    '北京频道': ['北京地区'],
    '福建频道': ['福建地区'],
    '甘肃频道': ['甘肃地区'],
    '广东频道': ['广东地区'],
    '广西频道': ['广西地区'],
    '贵州频道': ['贵州地区'],
    '海南频道': ['海南地区'],
    '河北频道': ['河北地区'],
    '河南频道': ['河南地区'],
    '黑龙江频道': ['黑龙江地区'],
    '湖北频道': ['湖北地区'],
    '湖南频道': ['湖南地区'],
    '吉林频道': ['吉林地区'],
    '江苏频道': ['江苏地区'],
    '江西频道': ['江西地区'],
    '辽宁频道': ['辽宁地区'],
    '内蒙古频道': ['内蒙古地区'],
    '宁夏频道': ['宁夏地区'],
    '青海频道': ['青海地区'],
    '山东频道': ['山东地区', '山东省级'],  # 新增：山东省级→山东频道
    '山西频道': ['山西地区'],
    '陕西频道': ['陕西地区'],
    '上海频道': ['上海地区'],
    '四川频道': ['四川地区'],
    '天津频道': ['天津地区'],
    '新疆频道': ['新疆地区'],
    '云南频道': ['云南地区'],
    '浙江频道': ['浙江地区'],
    '重庆频道': ['重庆地区'],

    # 特殊分类
    '港澳台频道': ['港澳台', '港澳代理', '湾区频道'],  # 港澳台/港澳代理→港澳台频道
    '央视频道': ['央视台'],              # 央视台→央视频道
    '卫视频道': ['卫视台', '省级卫视'],  # 卫视台→卫视频道
    '4K超高清': ['超清频道', '4K频道'],  # 超清频道/4K频道→4K超高清
    '央视高清': ['央视高清频道'],        # 央视高清频道→央视高清（单独分类）
    '动漫频道': ['动画频道'],
}

# 兼容旧映射：快速查找原始名称对应的目标名称（供代码调用）
group_title_reverse_mapping = {}
for target, originals in group_title_mapping.items():
    for original in originals:
        group_title_reverse_mapping[original] = target

