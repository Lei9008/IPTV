# 极简配置文件，仅填写核心所需参数
# 待抓取的直播源URL（可添加多个，支持公共M3U、自定义文本）
SOURCE_URLS = [
    "https://raw.githubusercontent.com/Lei9008/IPTV/main/input/source/movie.txt",
    # 可添加更多有效源地址
]

# 测速配置（可选，不填写则使用脚本默认值）
LATENCY_THRESHOLD = 50000  # 延迟阈值，超过该值视为无效
CONCURRENT_LIMIT = 20    # 并发数，不宜过大
TIMEOUT = 10             # 单个请求超时时间

