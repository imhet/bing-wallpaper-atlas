"""对 Bing CDN 候选分辨率后缀做 HEAD 验证。4 档并发探测（原串行限速版全程约 45 分钟，并发后约 1/4）。"""

from concurrent.futures import ThreadPoolExecutor

import requests

BASE = "https://www.bing.com"
RESOLUTION_SUFFIXES = [
    ("uhd", "_UHD.jpg"),
    ("fhd", "_1920x1080.jpg"),
    ("hd", "_1366x768.jpg"),
    ("thumb", "_400x240.jpg"),
]


def _probe(url, session):
    """True=可用 False=确认不存在 None=网络级失败（与「确认不存在」区分，避免抖动固化 false）。"""
    try:
        resp = session.head(url, timeout=10, allow_redirects=True)
        return resp.status_code == 200
    except (requests.RequestException, OSError):
        # OSError 兜底裸 ConnectionError（内置异常与 requests 异常是兄弟类）
        return None


def check_resolutions(urlbase, session=None):
    session = session or requests
    urls = [f"{BASE}{urlbase}{suffix}" for _, suffix in RESOLUTION_SUFFIXES]
    with ThreadPoolExecutor(max_workers=len(RESOLUTION_SUFFIXES)) as ex:
        results = list(ex.map(lambda u: _probe(u, session), urls))
    if any(r is None for r in results):
        # 任一档网络级失败即返回空让下轮回填重试——部分失败固化 false 会成为永久错标
        return {}
    return {key: (r is True) for (key, _), r in zip(RESOLUTION_SUFFIXES, results)}
