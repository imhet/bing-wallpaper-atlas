"""一次性重算：desc 无版权结构的记录，location 改为词典挖地名，region/tags 重导出。

背景：npanuhin 镜像源的 desc 是纯描述文本，parse_copyright 曾把整段描述按逗号
切开误存进 location（详情页「地点」显示长句、跳地图搜垃圾）。parse_copyright 修复后
（无 © 块返回空 location），存量数据用本脚本重算：

    python -m crawler.fix_locations --data-dir data

幂等：重算结果确定性，反复跑零 diff。有版权结构的记录一律不碰。
"""

import argparse
import logging
import os

from .copyright_parser import parse_copyright
from .geo_enrich import enrich_tags, extract_locations
from .regions import extract_region
from .storage import load_year, save_year, write_aggregations

log = logging.getLogger(__name__)


def recompute_record(rec, siblings_loc_text=""):
    """返回重算后的记录；无需变化（desc 有版权结构）时返回 None。

    地点多线挖掘，优先级：自身 title+desc → 同图组兄弟市场的 location（跨市场继承，
    挖成规范中文名）→ content_tags（VLM 打标的地名概念，desc 空的深史图靠它）→
    region 兜底（desc 归一出的国家写进 location 尾部）。
    """
    if parse_copyright(rec.get("desc") or "")["has_copyright"]:
        return None
    loc = extract_locations(f"{rec.get('title') or ''} {rec.get('desc') or ''}")
    if not loc and siblings_loc_text:
        loc = extract_locations(siblings_loc_text)
    if not loc:
        loc = extract_locations(" ".join(rec.get("content_tags") or []))
    if not loc and rec.get("region"):
        loc = [rec["region"]]
    rec = {**rec, "location": loc, "region": extract_region(loc, rec.get("desc")), "tags": []}
    return enrich_tags(rec)


def run(data_dir="data"):
    shards = {}
    for market in sorted(os.listdir(data_dir)):
        shard_dir = os.path.join(data_dir, market)
        if not os.path.isdir(shard_dir):
            continue
        for f in sorted(os.listdir(shard_dir)):
            if f.endswith(".json"):
                shards[(market, int(f[: -len(".json")]))] = load_year(data_dir, market, int(f[: -len(".json")]))

    def key_of(r):
        return r.get("imageKey") or r.get("urlbase") or ""

    # pass1：自身 title+desc / content_tags / region 兜底
    for records in shards.values():
        for i, rec in enumerate(records):
            new = recompute_record(rec)
            if new is not None:
                records[i] = new
    # pass2：同图组桥接——仍无地点的记录，从组内其他市场（重算后）的 location 继承
    by_key = {}
    for records in shards.values():
        for rec in records:
            by_key.setdefault(key_of(rec), []).append(rec)
    for records in shards.values():
        for i, rec in enumerate(records):
            if rec.get("location") or parse_copyright(rec.get("desc") or "")["has_copyright"]:
                continue
            sib_text = " ".join(
                " ".join(s["location"])
                for s in by_key[key_of(rec)]
                if s["id"] != rec["id"] and s["location"]
            )
            if not sib_text:
                continue
            new = recompute_record(rec, siblings_loc_text=sib_text)
            if new is not None:
                records[i] = new

    for (market, year), records in shards.items():
        orig = load_year(data_dir, market, year)
        if any(a is not b for a, b in zip(orig, records)):
            save_year(data_dir, market, year, records)
    loc_hit = sum(1 for records in shards.values() for r in records if r.get("location"))
    write_aggregations(data_dir)
    log.info("fix_locations done: with-location=%d/%d", loc_hit, sum(len(v) for v in shards.values()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="data")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    run(args.data_dir)


if __name__ == "__main__":
    main()
