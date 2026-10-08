"""市场分级配置：核心市场每日必抓且失败告警，扩展市场可整体启停。"""

CORE_MARKETS = ["zh-cn", "en-us"]
# ko-kr/zh-tw 保留在列：Bing 已无这两个市场的独立壁纸 feed（2026-10-08 Actions 美国
# 出口实测：www/kr/tw 域名与 cc 参数全部返回 ROW 全球图，见 probe workflow 历史），
# verify_mkt 每日预检会自动剔除。保留在列是为了 Bing 若恢复独立 feed 可自动开始收集。
EXTENDED_MARKETS = ["ja-jp", "en-gb", "de-de", "fr-fr", "ko-kr", "zh-tw"]
EXTENDED_ENABLED = True


def all_markets() -> list[str]:
    return CORE_MARKETS + (EXTENDED_MARKETS if EXTENDED_ENABLED else [])


def to_api_mkt(market: str) -> str:
    """'zh-cn' -> 'zh-CN'"""
    lang, region = market.split("-")
    return f"{lang}-{region.upper()}"
