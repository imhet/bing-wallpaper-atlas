"""niumoo/bing-wallpaper 仓库 images.json 回填源。

本地网络拉不到 raw.githubusercontent 时，可设环境变量
NIUMOO_JSON_URL=https://api.github.com/repos/niumoo/bing-wallpaper/contents/docs/images.json
（自动识别 GitHub contents API 的 base64 包装并解码）。
"""

import base64
import json
import os
import re
from datetime import datetime, timedelta

import requests

NIUMOO_URL = os.environ.get(
    "NIUMOO_JSON_URL",
    "https://raw.githubusercontent.com/niumoo/bing-wallpaper/main/docs/images.json",
)
_OHR_RE = re.compile(r"OHR\.[A-Za-z0-9]+?_[A-Z]{2}-[A-Z]{2}\d+")


def _shift_date(date_str):
    """niumoo 的 date 比 Bing startdate 系统性 +1 天（真实数据 8/8 实证），统一减一天对齐。坏值返回 None。"""
    try:
        return (datetime.strptime(date_str, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return None


class NiumooSource:
    name = "niumoo"

    def fetch(self, session=None):
        session = session or requests
        resp = session.get(NIUMOO_URL, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and "content" in data:  # GitHub contents API 包装
            data = json.loads(base64.b64decode(data["content"]))
        if not isinstance(data, list):
            raise ValueError(f"unexpected niumoo payload type: {type(data)}")
        today = datetime.now().strftime("%Y-%m-%d")
        out = []
        seen = set()  # (market, date) 去重：源数据有 51 组同日重复条目
        for item in data:
            region = item.get("region")
            if not isinstance(region, str) or not region:  # 坏条目丢自己，不能让整源报废
                continue
            m = _OHR_RE.search(item.get("url", "") or "")
            if not m:
                continue
            date = _shift_date(item.get("date"))
            if not date or date > today:  # 坏日期 / 未来日期丢弃
                continue
            key = (region.lower(), date)
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "market": region.lower(),
                "date": date,
                "urlbase": f"/th?id={m.group(0)}",
                "title": None,
                "desc": item.get("desc", "") or "",
                "copyrightlink": None,
                "quiz": None,
            })
        return out
