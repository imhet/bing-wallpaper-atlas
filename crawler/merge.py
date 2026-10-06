"""多来源记录的字段级互补合并。

规则：后面的源优先——非空字段覆盖前面的；空值不覆盖已有非空值。
"""


def _empty(v):
    return v is None or v == "" or v == []


def merge_records(*records):
    if not records:
        raise ValueError("no records to merge")
    merged = {}
    for rec in records:
        for key in ("market", "date"):
            if key in merged and rec.get(key) != merged[key]:
                raise ValueError(f"{key} conflict: {merged[key]!r} vs {rec.get(key)!r}")
        for k, v in rec.items():
            if not _empty(v):
                merged[k] = v
    return merged
