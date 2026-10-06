"""历史回填入口：跑全部源 → 按(市场,日期)合并 → 解析/校验/落盘 → 聚合。

幂等：已存在且带 resolutions 的记录跳过，可反复重跑。
"""

import argparse
import logging
import re

from .bing_api import fetch_market
from .copyright_parser import parse_copyright
from .image_key import extract_image_key
from .merge import merge_records
from .regions import extract_region
from .resolutions import check_resolutions
from .schema import validate_record
from .sources.bing_api_source import BingApiSource
from .sources.niumoo_source import NiumooSource
from .storage import load_year, upsert_record, write_aggregations

log = logging.getLogger(__name__)


def verify_mkt(markets, session=None):
    """逐市场预检 mkt 参数是否生效（防止本地网络把所有市场路由到 zh-CN feed）。返回通过的市场。"""
    ok = []
    for market in markets:
        try:
            recs = fetch_market(market, idx=0, n=1, session=session)
        except Exception as e:
            log.warning("mkt preflight failed (api error): %s: %s", market, e)
            continue
        expected = market.upper()  # zh-cn -> ZH-CN
        if recs and re.search(rf"_{expected}\d+", recs[0]["urlbase"] or ""):
            ok.append(market)
        else:
            log.warning("mkt preflight failed: %s 未返回本市场数据（疑似被网络位置覆盖），已剔除", market)
    return ok


def build_record(merged):
    loc = parse_copyright(merged.get("desc", ""))
    desc = merged.get("desc", "") or ""
    return {
        "id": f'{merged["market"]}-{merged["date"]}',
        "market": merged["market"],
        "date": merged["date"],
        "urlbase": merged.get("urlbase") or "",
        "imageKey": extract_image_key(merged.get("urlbase") or ""),
        "title": merged.get("title"),
        "desc": desc,
        "location": loc["location"],
        "region": extract_region(loc["location"], desc),
        "photographer": loc["photographer"],
        "gallery": loc["gallery"],
        "copyrightlink": merged.get("copyrightlink"),
        "quiz": merged.get("quiz"),
        "resolutions": {},
        "tags": [],
    }


def run_backfill(data_dir="data", check_res=True, markets=None):
    sources = [NiumooSource(), BingApiSource()]
    by_key = {}
    for src in sources:
        try:
            items = src.fetch()
        except Exception as e:  # 单个源失败不拖垮整个回填
            log.warning("source %s failed: %s", src.name, e)
            continue
        for r in items:
            if markets and r["market"] not in markets:
                continue
            by_key.setdefault((r["market"], r["date"]), []).append(r)

    valid_markets = set(verify_mkt(sorted({m for m, _ in by_key})))
    added = skipped = failed = 0
    for (market, date), recs in sorted(by_key.items()):
        if market not in valid_markets:
            continue
        try:
            merged = merge_records(*recs)
            rec = build_record(merged)
            year = int(date[:4])
            existing = [r for r in load_year(data_dir, market, year) if r["id"] == rec["id"]]
            if existing and existing[0].get("resolutions"):
                skipped += 1
                continue
            if check_res:
                rec["resolutions"] = check_resolutions(rec["urlbase"])
            validate_record(rec)
        except Exception as e:  # 单条坏记录只跳过，不中断整个回填
            failed += 1
            log.warning("record %s-%s failed: %s", market, date, e)
            continue
        if upsert_record(data_dir, rec):
            added += 1
    write_aggregations(data_dir)
    log.info("backfill done: added=%d skipped=%d failed=%d", added, skipped, failed)


def main():
    parser = argparse.ArgumentParser(description="Bing 壁纸历史回填")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--skip-resolution-check", action="store_true")
    parser.add_argument("--markets", default="", help="逗号分隔，仅回填这些市场（空=全部）")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    markets = [m.strip() for m in args.markets.split(",") if m.strip()] or None
    run_backfill(data_dir=args.data_dir, check_res=not args.skip_resolution_check, markets=markets)


if __name__ == "__main__":
    main()
