"""data/ 目录的分片读写与聚合文件生成。

布局：data/{market}/{year}.json 为按 date 升序的记录数组；
data/aggregations.json 为聚合文件。无时间戳字段保证零 diff。
"""

import json
from collections import Counter, defaultdict
from pathlib import Path


def year_shard_path(data_dir, market, year):
    return Path(data_dir) / market / f"{year}.json"


def load_year(data_dir, market, year):
    p = year_shard_path(data_dir, market, year)
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


def save_year(data_dir, market, year, records):
    p = year_shard_path(data_dir, market, year)
    p.parent.mkdir(parents=True, exist_ok=True)
    records = sorted(records, key=lambda r: r["date"])
    p.write_text(json.dumps(records, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def upsert_record(data_dir, rec):
    year = int(rec["date"][:4])
    records = load_year(data_dir, rec["market"], year)
    for i, existing in enumerate(records):
        if existing["id"] == rec["id"]:
            if existing == rec:
                return False
            records[i] = rec
            save_year(data_dir, rec["market"], year, records)
            return True
    records.append(rec)
    save_year(data_dir, rec["market"], year, records)
    return True


def load_all(data_dir):
    out = defaultdict(list)
    root = Path(data_dir)
    if not root.exists():
        return {}
    for market_dir in sorted(root.iterdir()):
        if not market_dir.is_dir():
            continue
        for f in sorted(market_dir.glob("*.json")):
            out[market_dir.name].extend(json.loads(f.read_text(encoding="utf-8")))
    return dict(out)


def write_aggregations(data_dir):
    all_recs = [r for recs in load_all(data_dir).values() for r in recs]

    def counted(field):
        c = Counter(r[field] for r in all_recs if r.get(field))
        return [{"name": k, "count": v} for k, v in c.most_common()]

    def counted_by(key):
        c = Counter(k for r in all_recs if (k := key(r)))
        return [{"name": k, "count": v} for k, v in sorted(c.items())]

    years_by_market = defaultdict(set)
    for r in all_recs:
        years_by_market[r["market"]].add(int(r["date"][:4]))
    agg = {
        "photographers": counted("photographer"),
        "regions": counted("region"),
        "markets": counted_by(lambda r: r["market"]),
        "years": counted_by(lambda r: int(r["date"][:4])),
        "months": counted_by(lambda r: int(r["date"][5:7])),
        "years_by_market": {m: sorted(ys) for m, ys in sorted(years_by_market.items())},
        "total": len(all_recs),
        "latest_date": max((r["date"] for r in all_recs), default=None),
    }
    p = Path(data_dir) / "aggregations.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(agg, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
