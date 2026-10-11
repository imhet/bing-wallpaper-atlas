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


def test_cjk_substring_blocked_by_negative_context(make_record):
    # 「格拉萨莱马」（西班牙小镇）含子串「拉萨」——否定上下文阻断误命中，
    # 不再连带挂上父行政区「西藏」混入西藏搜索
    rec = make_record(
        title="黄喉蜂虎",
        desc="格拉萨莱马山自然公园，加的斯，西班牙 (© X)",
        location=["格拉萨莱马山自然公园", "加的斯", "西班牙"],
    )
    tags = enrich_tags(rec)["tags"]
    assert "拉萨" not in tags and "西藏" not in tags and "lhasa" not in tags
    assert "西班牙" in tags


def test_lijiang_river_is_not_lijiang_city(make_record):
    # 桂林漓江（Lijiang River）与云南丽江同拼音：拉丁别名收窄后，
    # 英文漓江文本挂漓江组+广西层级，不再误挂丽江（云南）
    rec = make_record(
        title=None,
        desc="Karst mountains in Guilin and Lijiang River National Park, China (© X)",
        location=["Guilin", "Lijiang River National Park", "China"],
    )
    tags = enrich_tags(rec)["tags"]
    assert "丽江" not in tags and "云南" not in tags and "yunnan" not in tags
    assert "桂林" in tags and "广西" in tags


def test_marble_rock_is_not_dali_city(make_record):
    # 「魔鬼大理石保护区」（澳大利亚）含子串「大理」——否定上下文阻断，
    # 不再误挂大理组+层级父行政区云南
    rec = make_record(title=None, desc="魔鬼大理石保护区，澳大利亚 (© X)", location=["魔鬼大理石保护区", "澳大利亚"])
    tags = enrich_tags(rec)["tags"]
    assert "大理" not in tags and "云南" not in tags and "yunnan" not in tags
    assert "澳大利亚" in tags
