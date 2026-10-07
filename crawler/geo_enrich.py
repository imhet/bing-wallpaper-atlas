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

ALIASES_PATH = Path(__file__).parent / "geo_aliases.json"
MAX_TAGS = 12
_LATIN_RE = re.compile(r"[a-z0-9 '.\-]+")

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
    def __init__(self, alias_data):
        self.alias_data = alias_data
        self.pairs = [(name, *_compile(alts)) for name, alts in alias_data.items()]

    def match(self, text):
        return [
            name
            for name, cjk, latin_re in self.pairs
            if name in text or any(a in text for a in cjk) or (latin_re and latin_re.search(text))
        ]


_matcher = None


def _get_matcher():
    global _matcher
    if _matcher is None:
        _matcher = _Matcher(_load())
    return _matcher


def enrich_tags(record, matcher=None):
    """命中地名 → 追加规范名与全组别名到 tags（确定性截断到 MAX_TAGS，幂等）。"""
    m = matcher or _get_matcher()
    text = " ".join(
        [record.get("title") or "", record.get("desc") or "", " ".join(record.get("location") or [])]
    )
    tags = list(record.get("tags") or [])
    seen = set(tags)
    for name in m.match(text):
        for token in (name, *m.alias_data[name]):
            if token in seen:
                continue
            if len(tags) >= MAX_TAGS:
                return {**record, "tags": tags}
            seen.add(token)
            tags.append(token)
    return {**record, "tags": tags}


def main():
    parser = argparse.ArgumentParser(description="为存量记录补多语言地名 tags")
    parser.add_argument("--data-dir", default="data")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    matcher = _get_matcher()
    changed = 0
    for market, recs in sorted(load_all(args.data_dir).items()):
        for rec in recs:
            new = enrich_tags(rec, matcher)
            if new["tags"] != rec["tags"] and upsert_record(args.data_dir, new):
                changed += 1
    log.info("geo enrich done: changed=%d", changed)


if __name__ == "__main__":
    main()
