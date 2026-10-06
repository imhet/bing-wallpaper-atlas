from crawler.copyright_parser import parse_copyright


def test_standard_zh():
    r = parse_copyright("丹霞地貌，张掖国家地质公园，甘肃省，中国 (© Weiquan Lin/Getty Images)")
    assert r["photographer"] == "Weiquan Lin"
    assert r["gallery"] == "Getty Images"
    assert r["location"] == ["丹霞地貌", "张掖国家地质公园", "甘肃省", "中国"]


def test_no_gallery():
    r = parse_copyright("湖畔晨雾 (© 张三)")
    assert r["photographer"] == "张三"
    assert r["gallery"] is None


def test_english_sentence_location_is_single_item():
    r = parse_copyright("View of Edinburgh Castle from a churchyard in Scotland (© Chris Dorney/Alamy)")
    assert r["photographer"] == "Chris Dorney"
    assert r["gallery"] == "Alamy"
    assert r["location"] == ["View of Edinburgh Castle from a churchyard in Scotland"]


def test_trailing_date_stripped():
    r = parse_copyright("阿尔忒弥斯1号月球火箭，39B发射台，肯尼迪航天中心，佛罗里达州，2022年6月15日 (© EVA MARIE UZCATEGUI/Getty Images)")
    assert r["location"] == ["阿尔忒弥斯1号月球火箭", "39B发射台", "肯尼迪航天中心", "佛罗里达州"]
    assert r["photographer"] == "EVA MARIE UZCATEGUI"


def test_no_bracket_keeps_text_as_location():
    r = parse_copyright("神秘湖泊风光")
    assert r["photographer"] is None
    assert r["gallery"] is None
    assert r["location"] == ["神秘湖泊风光"]


def test_empty_and_none_never_raise():
    assert parse_copyright("") == {"photographer": None, "gallery": None, "location": []}
    assert parse_copyright(None) == {"photographer": None, "gallery": None, "location": []}


def test_nested_brackets_in_photographer_field():
    r = parse_copyright("湖上日出 (© 张三(李四)/Getty Images)")
    assert r["photographer"] == "张三"
    assert r["gallery"] == "Getty Images"


def test_pure_date_desc_location_empty():
    r = parse_copyright("2022年6月15日 (© 张三)")
    assert r["photographer"] == "张三"
    assert r["location"] == []
