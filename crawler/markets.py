"""市场分级配置：核心市场每日必抓且失败告警，扩展市场可整体启停。"""

CORE_MARKETS = ["zh-cn", "en-us"]
EXTENDED_MARKETS = ["ja-jp", "en-gb", "de-de", "fr-fr", "ko-kr", "zh-tw"]
EXTENDED_ENABLED = True


def all_markets() -> list[str]:
    return CORE_MARKETS + (EXTENDED_MARKETS if EXTENDED_ENABLED else [])


def to_api_mkt(market: str) -> str:
    """'zh-cn' -> 'zh-CN'"""
    lang, region = market.split("-")
    return f"{lang}-{region.upper()}"
