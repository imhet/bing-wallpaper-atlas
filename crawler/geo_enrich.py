"""多语言地名词典增强：文本命中地名时把「规范中文名 + 全组别名」写入 tags。

web 搜索字段（web/src/search.js FIELDS）已含 tags——中文「京都」、英文
"kyoto"、日文字形「軽井沢」等任意书写都能命中任意语言书写的同一地点。
词典见 geo_aliases.json：键为规范简体中文名，值为别名列表；拉丁别名统一
小写存储，匹配不区分大小写、按 \\b 词边界（防 "comparison" 误中 "paris"）；
CJK 别名按子串匹配。
"""

import argparse
import json
import logging
import re
from pathlib import Path

from .storage import load_all, upsert_record
from .regions import _LOWERED

ALIASES_PATH = Path(__file__).parent / "geo_aliases.json"
HIERARCHY_PATH = Path(__file__).parent / "geo_hierarchy.json"
MAX_TAGS = 12
_LATIN_RE = re.compile(r"[a-z0-9 '.\-]+")
# CJK 子串匹配的否定上下文：文本含干扰词时整个组跳过（「格拉萨莱马」含子串「拉萨」）
# 组级否定上下文：文本含这些子串时整组不命中（2026-10-11 全量排查 166 条误挂的产出）。
# CJK 按子串、拉丁按小写子串——「X德国家公园」不是德国、「Canton of Bern」不是广州
# （canton 裸别名已删）、「bohemian switzerland」是捷克不是瑞士。
_NEGATIVE_CONTEXT = {
    "拉萨": ["格拉萨莱马"],
    "大理": ["大理石", "大理岩"],  # 「魔鬼大理石保护区」（澳大利亚）不是云南大理
    "兰州": ["昆士兰", "马里兰"],  # 「昆士兰州」「马里兰州」的子串
    "达州": ["佛罗里达", "内华达", "明尼苏达"],  # 「佛罗里达州」等美国州名音译尾字
    "泉州": ["泉州立"],  # 彩虹泉州立公园（美国）
    "富士山": ["new zealand"],  # 新西兰塔拉纳基山在《最后的武士》里当过富士山替身，描述含类比提及
    "墨西哥": ["新墨西哥"],
    "爱尔兰": ["北爱尔兰"],  # 北爱尔兰属英国
    "芬兰": ["纽芬兰"],  # 加拿大纽芬兰岛
    "意大利": ["意大利卡"],  # Italica，西班牙古罗马城
    "德国": ["德国家", "莱德国"],  # 「泰/穆罕默德国家公园」「阿德莱德国际」的子串
    "法国": ["法国家", "mont blanc"],  # 「科法国家保护区」的子串；富士山文类比「勃朗峰（法国阿尔卑斯）」时不得归法国
    "富士山": ["new zealand", "apple"],  # 塔拉纳基山类比；"Fuji" 也是苹果品种（desc 提 apple 时是水果）
    "勃朗峰": ["fuji"],  # 富士山文类比勃朗峰（fuji 子串会误伤 fujian——二者同现概率≈0，可接受）
    "澳大利亚": ["澳大利亚花园"],  # 加州大学校园花园名
    "印度": ["印度尼西亚", "印度洋"],
    "瑞士": ["瑞士撒克逊", "波希米亚瑞士", "bohemian switzerland", "saxon switzerland"],
    "蒙古": ["蒙古自治州", "inner mongolia"],  # 内蒙古不是蒙古国
    "柏林": ["都柏林"],
    "罗马": ["罗马尼亚", "罗马式", "罗马风格"],
    "荷兰": ["荷兰港", "dutch harbor"],  # 阿拉斯加 Dutch Harbor
    "爱丁堡": ["爱丁堡茶园", "edinburgh tea estate"],  # 斯里兰卡茶园名
    "佛罗伦萨": ["florence, oregon"],  # 俄勒冈州 Florence 市
    "中国": ["lan su chinese garden"],  # 波特兰中式园林
    # 物种中文名含国名：动物/植物在世界各地都有
    "南非": ["南非剑羚"],
    "印度": ["印度尼西亚", "印度洋", "印度星龟"],
    "西班牙": ["西班牙苔藓"],
}

log = logging.getLogger(__name__)


def _load():
    return json.loads(ALIASES_PATH.read_text(encoding="utf-8"))


def _compile(alts):
    cjk, latin = [], []
    for a in alts:
        (latin if _LATIN_RE.fullmatch(a) else cjk).append(a)
    pattern = (
        re.compile(r"\b(" + "|".join(re.escape(a) for a in latin) + r")\b", re.IGNORECASE)
        if latin
        else None
    )
    return cjk, pattern


class _Matcher:
    def __init__(self, alias_data, hierarchy=None):
        self.alias_data = alias_data
        self.hierarchy = hierarchy or {}
        self.pairs = [(name, *_compile(alts)) for name, alts in alias_data.items()]

    def match(self, text):
        low = text.lower()
        return [
            name
            for name, cjk, latin_re in self.pairs
            if not any(neg in low for neg in _NEGATIVE_CONTEXT.get(name, []))
            and (name in text or any(a in text for a in cjk) or (latin_re and latin_re.search(text)))
        ]


_matcher = None


def _get_matcher():
    global _matcher
    if _matcher is None:
        hierarchy = (
            json.loads(HIERARCHY_PATH.read_text(encoding="utf-8"))
            if HIERARCHY_PATH.exists()
            else {}
        )
        _matcher = _Matcher(_load(), hierarchy)
    return _matcher


MAX_LOCATIONS = 5
# regions.py 的规范国家/地区名集合：extract_locations 排序时让国家殿后
_REGION_CANONICALS = frozenset(_LOWERED.values())


def extract_locations(text, matcher=None):
    """自由文本（无版权结构的 title+desc）挖地名：命中的规范中文名，最多 MAX_LOCATIONS 个。

    具体地名在前、国家名殿后（regions 规范表内的组是国家/地区，如「美国」——
    组内有 "united states" 这类长别名，纯按长度会把国家排到景点前面），
    其余按组内最长别名长度降序近似具体度。不做层级展开（tags 已展开，location
    保持文本真实出现的名字）。
    """
    m = matcher or _get_matcher()
    matched = m.match(text or "")
    matched.sort(key=lambda n: (n in _REGION_CANONICALS, -max(len(a) for a in (n, *m.alias_data[n]))))
    return matched[:MAX_LOCATIONS]


def enrich_tags(record, matcher=None):
    """命中地名 → 追加规范名与全组别名到 tags（确定性截断到 MAX_TAGS，幂等）。

    层级感知：命中子地名（张家界）时把父行政区（湖南）的全组别名一并写入，
    搜「湖南」即可召回文本里没有「湖南」二字的张家界记录。
    """
    m = matcher or _get_matcher()
    text = " ".join(
        [record.get("title") or "", record.get("desc") or "", " ".join(record.get("location") or [])]
    )
    tags = list(record.get("tags") or [])
    seen = set(tags)
    matched = m.match(text)
    # 层级展开：子地名命中 → 追加父行政区组（键与值都必须是 alias_data 组键）
    matched = list(dict.fromkeys([*matched, *(m.hierarchy[n] for n in matched if n in m.hierarchy)]))
    for name in matched:
        for token in (name, *m.alias_data[name]):
            if token in seen:
                continue
            if len(tags) >= MAX_TAGS:
                return {**record, "tags": tags}
            seen.add(token)
            tags.append(token)
    return {**record, "tags": tags}


def main(argv=None):
    parser = argparse.ArgumentParser(description="为存量记录补多语言地名 tags")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="先清空已有 tags 再重算：词典/匹配规则收紧后，清除存量里按旧规则写入的误报 tags"
        "（存量 tags 全部由本工具派生，重建安全——tests/test_geo_data.py 锁定结构）",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    matcher = _get_matcher()
    changed = 0
    for market, recs in sorted(load_all(args.data_dir).items()):
        for rec in recs:
            orig_tags = rec.get("tags")  # 比较基准是清空前的 tags——否则重算结果为空的记录永远不写回
            if args.rebuild:
                rec = {**rec, "tags": []}
            new = enrich_tags(rec, matcher)
            if new["tags"] != orig_tags and upsert_record(args.data_dir, new):
                changed += 1
    log.info("geo enrich done: changed=%d rebuild=%s", changed, args.rebuild)


if __name__ == "__main__":
    main()
