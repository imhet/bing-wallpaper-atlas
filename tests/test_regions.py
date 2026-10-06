from crawler.regions import extract_region


def test_zh_chain_tail_match():
    assert extract_region(["丹霞地貌", "张掖国家地质公园", "甘肃省", "中国"], "丹霞地貌，张掖国家地质公园，甘肃省，中国") == "中国"


def test_en_tail_match():
    assert extract_region(["Kasilof River", "Alaska", "USA"], "Kasilof River, Alaska, USA") == "美国"


def test_en_fulltext_match():
    assert extract_region(["View of Edinburgh Castle from a churchyard in Scotland"], "View of Edinburgh Castle from a churchyard in Scotland") == "英国"


def test_short_latin_alias_needs_word_boundary():
    # 'us' 不能因子串出现在 'russia' 里而误判
    assert extract_region([], "Kaliningrad, Russia") == "俄罗斯"
    assert extract_region([], "russett landscape") is None


def test_long_latin_alias_needs_word_boundary():
    # 'america' 不能因子串出现在 'American' 里而压过 canada
    assert extract_region(["Canadian Rockies"], "American robin perched in Canada") == "加拿大"


def test_continent_phrases_do_not_become_countries():
    # 南美/北美是地理区域不是国家；'South America' 不应命中 america→美国
    assert extract_region(["Amazon rainforest"], "Amazon rainforest in South America") is None
    assert extract_region([], "Seoul, South Korea") == "韩国"  # 负向短语只挡特定别名


def test_no_match_returns_none():
    assert extract_region(["神秘湖泊风光"], "神秘湖泊风光") is None
    assert extract_region([], "") is None
