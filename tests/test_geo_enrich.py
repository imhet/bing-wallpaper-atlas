import pytest

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


# 2026-10-11 全量排查（166 条误挂）后的否定上下文集：CJK 子串与拉丁专名统一走 _NEGATIVE_CONTEXT。
# 每例 = (desc 文本, 不得出现的组列表, 应保留的组或 None)；banned 组断言到全组 token。
NEGATIVE_CONTEXT_CASES = [
    # --- 裸拉丁别名删除后的行为锁定 ---
    ("Staubbach Falls at Lauterbrunnen, Canton of Bern, Switzerland", ["广州"], "瑞士"),
    ("heart-shaped rock island off the coast of sydney, australia", ["冰岛"], "澳大利亚"),
    ("coral reef in the indian ocean, overseas department of france, mayotte", ["印度"], "法国"),
    ("african bush elephants at masai mara national reserve, kenya", ["南非"], "肯尼亚"),
    ("american robin perched on a branch in canada", ["美国"], "加拿大"),
    ("french street artist jr, rome, italy", ["法国"], "罗马"),
    ("spanish moss in the okefenokee swamp, georgia, usa", ["西班牙"], "美国"),
    ("swedish telescope at la silla eso observatory, chile", ["瑞典"], None),
    ("koala in a eucalyptus tree, great otway national park, australia (© x - site.co.uk)", ["英国"], None),
    ("rio grande, big bend national park, texas, usa", ["里约热内卢"], "美国"),
    # --- 专名类比提及（2026-10-13 深史回填引入）：新西兰塔拉纳基山在《最后的武士》里当过富士山替身 ---
    ("Taranaki had a star turn as Mount Fuji in background shots for 'The Last Samurai', New Zealand", ["富士山"], None),
    # --- CJK 子串误命中 ---
    ("白天堂海滩，圣灵群岛，昆士兰州，澳大利亚", ["兰州"], None),
    ("英仙座流星雨，内华达州，美国", ["达州", "四川"], "美国"),
    ("三一学院图书馆，都柏林，爱尔兰", ["柏林"], "都柏林"),
    ("锡比乌圣诞市场，罗马尼亚", ["罗马"], None),
    ("地牢省立公园，纽芬兰和拉布拉多省，加拿大", ["芬兰"], "加拿大"),
    ("白沙国家公园的日落，新墨西哥州，美国", ["墨西哥"], "美国"),
    ("巨人之路，北爱尔兰，英国", ["爱尔兰"], "英国"),
    ("泰德国家公园的日落，特内里费岛，西班牙", ["德国"], "西班牙"),
    ("科法国家野生动物保护区，亚利桑那州，美国", ["法国"], "美国"),
    ("意大利卡，桑蒂蓬塞的一座古罗马城遗址，塞维利亚，西班牙", ["意大利"], "西班牙"),
    ("彩虹泉州立公园的彩虹河，佛罗里达州，美国", ["泉州"], "美国"),
    ("澳大利亚花园里的蜂鸟，加州大学圣克鲁兹分校植物园，美国", ["澳大利亚"], "美国"),
    # --- 拉丁专名否定（否定上下文不止 CJK） ---
    ("bohemian switzerland national park near tisa, czech republic", ["瑞士"], None),
    ("dinosaur museum of erenhot in inner mongolia, china", ["蒙古"], "中国"),
    # --- 专名撞名 ---
    ("座头鲸家族，荷兰港，阿拉斯加州，美国", ["荷兰"], "美国"),
    ("爱丁堡茶园, 努沃勒埃利耶, 斯里兰卡", ["爱丁堡"], "斯里兰卡"),
    ("heceta head light, florence, oregon, usa", ["佛罗伦萨"], None),
    ("koi fish, lan su chinese garden, portland, oregon", ["中国"], None),
    # --- 物种中文名含国名 ---
    ("沙丘中的南非剑羚，纳米比亚", ["南非"], "纳米比亚"),
    ("印度星龟，斯里兰卡", ["印度"], "斯里兰卡"),
    ("奥克弗诺基沼泽木板路上的西班牙苔藓，佐治亚州，美国", ["西班牙"], "美国"),
]


@pytest.mark.parametrize("desc,banned_groups,kept", NEGATIVE_CONTEXT_CASES)
def test_negative_context_blocklist(make_record, desc, banned_groups, kept):
    import json
    from crawler.geo_enrich import _load

    alias_data = _load()
    rec = make_record(title=None, desc=desc, location=["Somewhere"])
    tags = enrich_tags(rec)["tags"]
    for group in banned_groups:
        banned_tokens = {group, *alias_data[group]}
        leak = banned_tokens & set(tags)
        assert not leak, f"「{desc[:30]}…」误挂 {group} 组: {leak}"
    if kept:
        assert kept in tags, f"「{desc[:30]}…」应保留地名「{kept}」，实际 {tags}"


def test_arches_generic_word_no_longer_matches(make_record):
    # 「拱门」组收窄为国家公园全名：泛拱门图不再误挂；真 NP 文本照常命中
    generic = enrich_tags(make_record(title=None, desc="塔斯曼拱门，塔斯马尼亚州，澳大利亚 (© X)", location=["Somewhere"]))["tags"]
    assert "拱门国家公园" not in generic
    np_rec = enrich_tags(make_record(title=None, desc="精致拱门，拱门国家公园，犹他州，美国 (© X)", location=["Somewhere"]))
    assert "拱门国家公园" in np_rec["tags"]


def test_rebuild_writes_back_when_enrich_result_is_empty(tmp_path, make_record):
    # --rebuild 的比较基准必须是清空前的 tags：重算结果为空的记录（词典收紧后旧误报应清零）
    # 也要写回——否则已删别名（island 等）的残留 tags 永远留在库里，且每轮 rebuild 都被跳过
    from crawler.geo_enrich import main as enrich_main
    from crawler.storage import load_year, save_year

    rec = {**make_record(
        title=None,
        desc="lighthouse at cape aniva, sakhalin island, russia (© X)",
        location=["Cape Aniva"],
    ), "id": "en-us-2021-04-03", "market": "en-us", "date": "2021-04-03",
        "tags": ["冰岛", "iceland", "island", "アイスランド", "冰島"]}
    save_year(str(tmp_path), "en-us", 2021, [rec])

    enrich_main(["--data-dir", str(tmp_path), "--rebuild"])

    out = load_year(str(tmp_path), "en-us", 2021)
    assert out[0]["tags"] == [], f"rebuild 后残留: {out[0]['tags']}"
