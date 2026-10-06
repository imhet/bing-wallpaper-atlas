"""Bing 官方接口回填源（补充 title/copyrightlink 等富字段，仅最近约 15 天）。"""

from ..bing_api import fetch_market
from ..markets import CORE_MARKETS, EXTENDED_ENABLED, EXTENDED_MARKETS


class BingApiSource:
    name = "bing-api"

    def fetch(self):
        markets = list(CORE_MARKETS) + (EXTENDED_MARKETS if EXTENDED_ENABLED else [])
        out = []
        for market in markets:
            out.extend(fetch_market(market, idx=0, n=8))
        return out
