from crawler.geo_enrich import enrich_tags, MAX_TAGS

# make_record 默认 location 含 Zhangjiajie（词典命中项），无命中场景必须显式中性化
NEUTRAL = dict(desc="(© Test)", location=["Somewhere"])


def test_enriches_tags_from_mixed_language_text(make_record):
    # 英文书写的记录：命中别名 → tags 写入规范中文名 + 全组别名，中文查询即可命中
    rec = make_record(title="Autumn in Kyoto", desc="Temple scene, Japan (© X)", location=["Kyoto"])
    tags = enrich_tags(rec)["tags"]
    assert "京都" in tags and "日本" in tags
    assert "kyoto" in tags and "japan" in tags


def test_latin_matches_word_boundaries_case_insensitive(make_record):
    assert "巴黎" in enrich_tags(make_record(title="PARIS at dawn", **NEUTRAL))["tags"]
    # comparison 含 paris 子串，无词边界不得误报
    assert enrich_tags(make_record(title="A comparison of lenses", **NEUTRAL))["tags"] == []


def test_cjk_variant_match(make_record):
    # 日文字形「軽井沢」「長野」命中简体规范名，桥接中日查询
    rec = make_record(title="軽井沢の朝", desc="軽井沢, 長野 (© X)")
    tags = enrich_tags(rec)["tags"]
    assert "轻井泽" in tags and "karuizawa" in tags
    assert "长野" in tags


def test_cap_and_idempotent(make_record):
    text = "Tokyo Kyoto Osaka Nagoya Sapporo Fukuoka Hiroshima Sendai Nara Okinawa Hokkaido"
    out = enrich_tags(make_record(title=text, **NEUTRAL))
    assert len(out["tags"]) == MAX_TAGS  # 超上限确定性截断
    assert enrich_tags(out)["tags"] == out["tags"]  # 重复 enrich 不重复追加


def test_no_match_keeps_tags_untouched(make_record):
    rec = make_record(title="Nothing matchable", tags=["已有"], **NEUTRAL)
    out = enrich_tags(rec)
    assert out["tags"] == ["已有"]


def test_hierarchy_parent_aliases_injected(make_record):
    # 层级词典：命中子地名（张家界）→ 父行政区（湖南）全组别名一并写入，
    # 搜「湖南」即可通过 tags 召回张家界（记录文本里并没有「湖南」二字）
    rec = make_record(title="Wulingyuan sandstone pillars", desc="Zhangjiajie, China (© X)", location=["张家界"])
    tags = enrich_tags(rec)["tags"]
    assert "张家界" in tags
    assert "湖南" in tags and "hunan" in tags
