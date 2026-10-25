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


def recompute_record(rec):
    """返回重算后的记录；无需变化（desc 有版权结构）时返回 None。"""
    if parse_copyright(rec.get("desc") or "")["has_copyright"]:
        return None
    loc = extract_locations(f"{rec.get('title') or ''} {rec.get('desc') or ''}")
    rec = {**rec, "location": loc, "region": extract_region(loc, rec.get("desc")), "tags": []}
    return enrich_tags(rec)


def run(data_dir="data"):
    changed = loc_hit = 0
    for market in sorted(os.listdir(data_dir)):
        shard_dir = os.path.join(data_dir, market)
        if not os.path.isdir(shard_dir):
            continue
        for f in sorted(os.listdir(shard_dir)):
            if not f.endswith(".json"):
                continue
            path_year = int(f[: -len(".json")])
            records = load_year(data_dir, market, path_year)
            out = []
            dirty = False
            for rec in records:
                new = recompute_record(rec)
                if new is None:
                    out.append(rec)
                    continue
                dirty = True
                changed += 1
                loc_hit += bool(new["location"])
                out.append(new)
            if dirty:
                save_year(data_dir, market, path_year, out)
    write_aggregations(data_dir)
    log.info("fix_locations done: changed=%d with-location=%d", changed, loc_hit)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="data")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    run(args.data_dir)


if __name__ == "__main__":
    main()
