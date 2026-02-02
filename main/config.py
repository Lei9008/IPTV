# 优化版配置文件，适配高成功率需求，无需修改，直接和脚本放在同一目录
# 待抓取的直播源URL（可添加多个，支持公共M3U、自定义文本）
SOURCE_URLS = [
    "https://raw.githubusercontent.com/Lei9008/IPTV/main/input/source/movie.txt",
    # 可添加更多有效源地址
]

# 播放验证配置（已优化，优先保障成功率）
LATENCY_THRESHOLD = 3000  # 延迟阈值放宽到3000ms，覆盖大部分正常源
CONCURRENT_LIMIT = 10     # 降低并发数，避免被服务器封禁
TIMEOUT = 35              # 超时时间加长到35s，给足M3U8加载时间
RETRY_TIMES = 1           # 减少重试次数，避免加重服务器压力
ALLOW_REDIRECTS = True    # 开启重定向，兼容302/307跳转的M3U8（补充，避免报错）
MAX_REDIRECTS = 5         # 最大重定向次数（补充，避免报错）
