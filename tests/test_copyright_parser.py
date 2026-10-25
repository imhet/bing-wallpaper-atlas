from crawler.copyright_parser import parse_copyright


def test_standard_zh():
    r = parse_copyright("丹霞地貌，张掖国家地质公园，甘肃省，中国 (© Weiquan Lin/Getty Images)")
    assert r["photographer"] == "Weiquan Lin"
    assert r["gallery"] == "Getty Images"
    assert r["location"] == ["丹霞地貌", "张掖国家地质公园", "甘肃省", "中国"]
    assert r["has_copyright"] is True


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


def test_no_bracket_means_no_location():
    # 无版权结构（镜像深史/乱码 desc）= 该源不提供地点：纯描述文本不得误当地点，
    # 由 geo_enrich.extract_locations 从文本挖地名填充（build_record 接线）
    r = parse_copyright("神秘湖泊风光")
    assert r["photographer"] is None
    assert r["gallery"] is None
    assert r["location"] == []
    assert r["has_copyright"] is False


def test_empty_and_none_never_raise():
    assert parse_copyright("") == {"photographer": None, "gallery": None, "location": [], "has_copyright": False}
    assert parse_copyright(None) == {"photographer": None, "gallery": None, "location": [], "has_copyright": False}


def test_nested_brackets_in_photographer_field():
    r = parse_copyright("湖上日出 (© 张三(李四)/Getty Images)")
    assert r["photographer"] == "张三"
    assert r["gallery"] == "Getty Images"


def test_pure_date_desc_location_empty():
    r = parse_copyright("2022年6月15日 (© 张三)")
    assert r["photographer"] == "张三"
    assert r["location"] == []
