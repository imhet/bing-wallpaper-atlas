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
