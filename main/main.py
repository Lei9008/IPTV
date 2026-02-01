import requests

def get_url_content(url):
    """
    发送网络请求，获取指定URL的文本内容
    :param url: 目标网络链接
    :return: 链接对应的文本内容（获取失败返回空字符串）
    """
    try:
        # 发送GET请求，设置超时时间避免无限等待，添加请求头模拟浏览器（防止部分站点拦截）
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=30)
        # 验证请求是否成功（状态码200表示成功）
        response.raise_for_status()
        # 设置编码（自动识别文本编码，避免中文乱码）
        response.encoding = response.apparent_encoding
        print(f"成功获取链接内容：{url}")
        return response.text
    except Exception as e:
        print(f"获取链接内容失败：{url}，错误信息：{str(e)}")
        return ""

def merge_url_contents(url_list, save_file_path="merged_result.txt"):
    """
    合并多个URL的文本内容，并保存到本地文件
    :param url_list: 待获取内容的URL列表
    :param save_file_path: 合并结果保存的本地文件路径
    :return: 合并后的完整文本内容
    """
    # 初始化合并结果
    merged_content = ""
    
    for url in url_list:
        content = get_url_content(url)
        if content:
            # 每个链接的内容后添加一个空行分隔，避免内容粘连（可根据需要删除这行）
            merged_content += content + "\n\n"
    
    # 将合并结果保存到本地文件
    if merged_content:
        with open(save_file_path, "w", encoding="utf-8") as f:
            f.write(merged_content)
        print(f"合并完成，结果已保存到：{save_file_path}")
    else:
        print("未获取到有效内容，合并失败")
    
    return merged_content

# 主程序执行
if __name__ == "__main__":
    # 定义需要处理的两个链接
    target_urls = [
        "https://raw.githubusercontent.com/Lei9008/iptv_selfuse/master/output/user_result.txt",
        "https://raw.githubusercontent.com/Lei9008/IPTV/main/input/source/Ku9-IPTV-source.txt"
    ]
    
    # 调用函数合并内容
    merge_url_contents(target_urls)
