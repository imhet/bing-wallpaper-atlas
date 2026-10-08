"""Bing 官方接口回填源（补充 title/copyrightlink 等富字段，仅最近约 15 天）。"""

import logging

from ..bing_api import fetch_market
from ..markets import CORE_MARKETS, EXTENDED_ENABLED, EXTENDED_MARKETS

log = logging.getLogger(__name__)


class BingApiSource:
    name = "bing-api"

    def fetch(self):
        markets = list(CORE_MARKETS) + (EXTENDED_MARKETS if EXTENDED_ENABLED else [])
        out = []
        for market in markets:
            try:
                out.extend(fetch_market(market, idx=0, n=8))
            except Exception as e:  # 单市场失败只丢该市场，不能让整源报废
                log.warning("bing-api source: market %s failed: %s", market, e)
        return out
