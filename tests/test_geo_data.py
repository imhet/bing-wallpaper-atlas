"""地名词典数据一致性校验。geo_aliases.json / geo_hierarchy.json 是手维护数据，
扩词典时容易手滑——这里锁住结构约束，坏数据在测试期炸而不是上线后静默失效。"""

import json
from pathlib import Path

CRAWLER_DIR = Path(__file__).parent.parent / "crawler"


def _load():
    aliases = json.loads((CRAWLER_DIR / "geo_aliases.json").read_text(encoding="utf-8"))
    hierarchy = json.loads((CRAWLER_DIR / "geo_hierarchy.json").read_text(encoding="utf-8"))
    return aliases, hierarchy


def test_group_names_and_aliases_nonempty():
    aliases, _ = _load()
    for name, alts in aliases.items():
        assert name.strip(), "存在空组名"
        assert isinstance(alts, list) and alts, f"组「{name}」别名列表为空"
        assert all(a and str(a).strip() for a in alts), f"组「{name}」存在空别名"


def test_hierarchy_targets_are_alias_groups():
    # 层级展开的键与值都必须是词典组键（geo_enrich 直接按组键取别名）——挂空则搜索端零效果
    aliases, hierarchy = _load()
    for child, parent in hierarchy.items():
        assert child in aliases, f"层级子地名「{child}」不在词典组里，层级挂空"
        assert parent in aliases, f"层级 {child}→{parent}：父行政区「{parent}」不是词典组键"


def test_no_ambiguous_group_names():
    # 歧义剔除原则：CJK 是子串匹配，常见他义词不建组（朝阳=辽宁市/常见词、阿里=电商……）。
    # 例外「黄石」：作为知名景区组有意保留——语料里 100% 是黄石国家公园（Yellowstone），
    # 无湖北黄石市图；其余同名市（如大冶所在的黄石）在壁纸语料中不存在
    aliases, _ = _load()
    banned = {"朝阳", "中山", "北海", "山南", "安康", "中卫", "来宾", "宿州", "抚州", "阿里"}
    clash = banned & aliases.keys()
    assert not clash, f"歧义地名回归词典: {clash}"


def test_province_groups_have_traditional_aliases():
    # 繁体用户搜索盲区：省组名含简繁差异字形时必须补繁体别名（搜「廣西」≠搜「广西」）
    aliases, _ = _load()
    expected = {
        "云南": "雲南", "内蒙古": "內蒙古", "宁夏": "寧夏", "山东": "山東", "广东": "廣東",
        "广西": "廣西", "江苏": "江蘇", "甘肃": "甘肅", "贵州": "貴州", "辽宁": "遼寧",
        "陕西": "陝西", "黑龙江": "黑龍江", "台湾": "臺灣",
    }
    missing = {p: t for p, t in expected.items() if t not in aliases.get(p, [])}
    assert not missing, f"省级组缺繁体别名: {missing}"


def test_no_dangerous_common_word_latin_aliases():
    # 危险裸词黑名单：这些英文常用词作别名会吞掉大量无关图——
    # island→冰岛吞英文「岛屿」62 条、indian→印度吞 Indian Ocean、canton→广州吞瑞士 Canton of Bern、
    # uk→英国吞摄影师 credit「.co.uk」……词边界挡不住常用词本身（2026-10-11 全量排查 166 条误挂）
    aliases, _ = _load()
    banned = {"canton", "island", "indian", "african", "american", "french", "spanish", "swedish", "uk", "rio"}
    hits = {a: g for g, alts in aliases.items() for a in alts if a in banned}
    assert not hits, f"危险裸词别名回归: {hits}"


def test_arches_group_requires_full_park_name():
    # 「拱门」是普通名词：塔斯曼拱门（澳）/圣路易斯拱门/新西兰拱门群岛……只有国家公园全名可作别名；
    # 搜索端不受损——查询「拱门」的二元组仍命中「拱门国家公园」
    aliases, _ = _load()
    assert set(aliases.get("拱门国家公园", [])) == {"arches national park", "拱門國家公園"}
    assert "拱门" not in aliases, "裸「拱门」组名会吞掉一切拱门类地物"


def test_lijiang_city_group_has_no_bare_latin_alias():
    # 丽江/漓江同拼音（lijiang）：英文语料里 lijiang 只出现在漓江——
    # 丽江组不得保留裸 'lijiang' 别名，否则桂林图误挂云南
    aliases, _ = _load()
    assert "lijiang" not in aliases.get("丽江", []), "丽江组的裸 lijiang 别名会误吃英文漓江文本"
    assert "lijiang river" in aliases.get("漓江", []), "漓江组应承接 lijiang river 召回"
