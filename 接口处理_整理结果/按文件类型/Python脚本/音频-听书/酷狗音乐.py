import requests

m3u_url = "https://kugou.445569.xyz/live.m3u"

def get_m3u_content(url: str):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()  # http状态码异常抛异常
        content = resp.text
        return True, content
    except requests.exceptions.RequestException as e:
        # 网络/解析/访问失败
        return False, f"获取失败: {str(e)}"


if __name__ == "__main__":
    ok, result = get_m3u_content(m3u_url)
    if ok:
        print("=====m3u源内容=====")
        print(result)
        # 你可以在这里做进一步解析：按行过滤#EXT开头注释，提取真实播放地址
        lines = [line.strip() for line in result.splitlines() if line.strip() and not line.startswith("#")]
        print("\n====提取出来的播放链接====")
        for item in lines:
            print(item)
    else:
        print(result)
#（注：内容由AI生成）
