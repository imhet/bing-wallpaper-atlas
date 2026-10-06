"""Bing HPImageArchive 接口客户端（免密钥，仅最近约 15 天）。"""

import time

import requests

from .markets import to_api_mkt

API_URL = "https://www.bing.com/HPImageArchive.aspx"


class BingApiError(RuntimeError):
    pass


def _normalize(img, market):
    """返回 raw 记录；单条坏数据（如 startdate 缺失）返回 None，由调用方跳过。"""
    sd = str(img.get("startdate", ""))
    if len(sd) != 8 or not sd.isdigit():
        return None
    return {
        "market": market,
        "date": f"{sd[0:4]}-{sd[4:6]}-{sd[6:8]}",
        "urlbase": img.get("urlbase"),
        "title": img.get("title") or None,
        "desc": img.get("copyright", ""),
        "copyrightlink": img.get("copyrightlink") or None,
        "quiz": img.get("quiz") or None,
    }


def fetch_market(market, idx=0, n=8, timeout=15, max_retries=3, session=None):
    session = session or requests
    params = {"format": "js", "idx": idx, "n": n, "mkt": to_api_mkt(market)}
    last_err = None
    for attempt in range(max_retries):
        try:
            resp = session.get(API_URL, params=params, timeout=timeout)
            resp.raise_for_status()
            records = (_normalize(img, market) for img in resp.json().get("images", []))
            return [r for r in records if r]  # 坏记录跳过，重试只留给网络类错误
        except (requests.RequestException, ValueError, RuntimeError) as e:
            last_err = e
            time.sleep(2 ** attempt)
    raise BingApiError(f"{market} idx={idx} failed after {max_retries} attempts: {last_err}") from last_err
