import pytest

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


def test_english_china_aliases():
    # en-us copyright 是英文句子：'..., China (© ...)' 必须命中中国（en-us 回填前必须修复）
    assert extract_region([], "Zhangjiakou, China (© John Doe)") == "中国"
    assert extract_region([], "Victoria Harbour in Hong Kong") == "中国"
    assert extract_region([], "Ruins of St. Paul's in Macau") == "中国"


def test_mongol_autonomous_prefecture_is_not_mongolia():
    # 中国行政区划名里的「蒙古」不是蒙古国；否定后全文应回退命中「中国」
    loc = ["夏季的赛里木湖", "博尔塔拉蒙古自治州博乐县", "中国新疆维吾尔自治区"]
    assert extract_region(loc, "，".join(loc)) == "中国"


def test_inner_mongolia_is_not_mongolia():
    # 无独立「中国」段时，「内蒙古」应作为独立别名归中国，而不是落到「蒙古」
    loc = ["额济纳旗胡杨林", "内蒙古自治区阿拉善盟"]
    assert extract_region(loc, "，".join(loc)) == "中国"


def test_british_columbia_is_not_colombia():
    # 「不列颠哥伦比亚」含子串「哥伦比亚」——加拿大图不得误归南美哥伦比亚
    assert extract_region(["考伊琴山谷的薄雾", "温哥华岛", "加拿大不列颠哥伦比亚省"], "考伊琴山谷的薄雾，温哥华岛，加拿大不列颠哥伦比亚省 (© X)") == "加拿大"
