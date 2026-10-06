from crawler.markets import CORE_MARKETS, EXTENDED_MARKETS, all_markets, to_api_mkt


def test_core_markets():
    assert CORE_MARKETS == ["zh-cn", "en-us"]


def test_extended_markets():
    assert EXTENDED_MARKETS == ["ja-jp", "en-gb", "de-de", "fr-fr", "ko-kr", "zh-tw"]


def test_all_markets_contains_both_tiers():
    markets = all_markets()
    assert "zh-cn" in markets and "ja-jp" in markets


def test_to_api_mkt():
    assert to_api_mkt("zh-cn") == "zh-CN"
    assert to_api_mkt("en-us") == "en-US"
