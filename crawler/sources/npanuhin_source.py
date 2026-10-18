"""npanuhin/Bing-Wallpaper-Archive 深史回填源（en-us 自 2010-01-01，唯一可靠历史归档）。

en-us 只取 niumoo 起点（2021-02）之前的部分，重叠段不进 backfill（与 skip-guard 双防线）。
ja-jp/de-de/fr-fr/en-gb 归档 2024-04 起，end_date 参数化挡住与本地每日增量的重叠段
（2026-09-29 起）。老图无 Bing OHR ID，urlbase 存镜像绝对 URL——schema pattern /
resolutions 探测 / 前端 imageUrl 均已兼容该形态。深史条目 2010-2015 无 description
（当年 Bing 首页 HTML 只嵌标题，描述在 AJAX 弹层里从未被快照保存——经查证的历史事实，
非归档缺失）。
"""

import os
from datetime import datetime

import requests

NPANUHIN_URL = os.environ.get("NPANUHIN_JSON_URL", "https://bing.npanuhin.me/US-en.json")
MARKET = "en-us"  # 归档的 US-en
END_DATE = "2021-02-01"  # niumoo 的 en-us 起点
EXTENSION_END_DATE = "2026-09-29"  # ja/de/fr/gb 的本地每日增量起点

_DATE_FMT = "%Y-%m-%d"


def _normalize_copyright(text):
    """'© X/Y' 原样；深史老条目的尾部 © 归一到头部（版权解析器要求 (© X/Y) 括号格式）；空值 None。"""
    text = (text or "").strip()
    if not text:
        return None
    if text.endswith("©"):
        text = f"© {text[:-1]}".strip()
    return text


class NpanuhinSource:
    name = "npanuhin"
    needs_mkt_check = False  # 数据来自镜像归档而非 Bing 接口，不存在网络位置路由污染

    def __init__(self, market=MARKET, end_date=END_DATE):
        self.market = market
        self.end_date = end_date
        lang, region = market.split("-")
        self.slug = f"{region.upper()}-{lang}"  # en-us → US-en、ja-jp → JP-ja
        # NPANUHIN_JSON_URL 环境变量是全局测试后门：设置时覆盖所有实例
        self.url = NPANUHIN_URL if os.environ.get("NPANUHIN_JSON_URL") else f"https://bing.npanuhin.me/{self.slug}.json"

    def fetch(self, session=None):
        session = session or requests
        resp = session.get(self.url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list):
            raise ValueError(f"unexpected npanuhin payload type: {type(data)}")
        today = datetime.now().strftime(_DATE_FMT)
        out = []
        seen = set()  # 归档存在少量同日重复条目（6124 条 vs 6111 天）
        for item in data:
            try:
                date = datetime.strptime((item.get("date") or "").strip(), _DATE_FMT).strftime(_DATE_FMT)
            except (ValueError, AttributeError):
                continue  # 缺失/坏日期丢自己，不能让整源报废
            url = (item.get("url") or "").strip()
            if not url.startswith("https://") or date > today or date >= self.end_date:
                continue
            if date in seen:
                continue
            seen.add(date)
            title = item.get("title")
            desc = item.get("description") or ""
            # 少量归档条目只有 caption（title/description 皆空）：用它兜底描述，
            # 否则详情页标题取 title || desc 为空；已有 title 的记录不受影响
            if not title and not desc:
                desc = item.get("caption") or ""
            out.append({
                "market": self.market,
                "date": date,
                "urlbase": url,
                "title": title,
                "desc": desc,
                "copyright": _normalize_copyright(item.get("copyright")),
                "copyrightlink": None,
                "quiz": None,
            })
        return out
