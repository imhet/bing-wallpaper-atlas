"""对 Bing CDN 候选分辨率后缀做 HEAD 验证。限速 5 req/s。"""

import time

import requests

BASE = "https://www.bing.com"
RESOLUTION_SUFFIXES = [
    ("uhd", "_UHD.jpg"),
    ("fhd", "_1920x1080.jpg"),
    ("hd", "_1366x768.jpg"),
    ("thumb", "_400x240.jpg"),
]
REQUEST_INTERVAL = 0.2


def check_resolutions(urlbase, session=None, interval=REQUEST_INTERVAL):
    session = session or requests
    out = {}
    errors = 0
    for key, suffix in RESOLUTION_SUFFIXES:
        url = f"{BASE}{urlbase}{suffix}"
        try:
            resp = session.head(url, timeout=10, allow_redirects=True)
            out[key] = resp.status_code == 200
        except (requests.RequestException, OSError):
            # OSError 兜底裸 ConnectionError（内置异常与 requests 异常是兄弟类）
            out[key] = False
            errors += 1
        time.sleep(interval)
    if errors == len(RESOLUTION_SUFFIXES):
        return {}  # 全部网络级失败视为系统性故障：返回空让下轮回填重试，不固化 false
    return out
