"""每日增量入口：核心市场必抓（失败告警退出码 1），扩展市场尽力抓。

n=8 窗口容忍漏抓；无新数据时不产生 git diff（Actions 据此跳过部署）。
"""

import argparse
import logging
import sys

from .backfill import build_record, verify_mkt
from .bing_api import BingApiError, fetch_market
from .markets import CORE_MARKETS, EXTENDED_ENABLED, EXTENDED_MARKETS
from .resolutions import check_resolutions
from .schema import validate_record
from .storage import upsert_record, write_aggregations

log = logging.getLogger(__name__)


def ingest_market(market, data_dir):
    added = 0
    for rawrec in fetch_market(market, idx=0, n=8):
        try:
            rec = build_record(rawrec)
            rec["resolutions"] = check_resolutions(rec["urlbase"])
            validate_record(rec)
        except Exception as e:  # 单条坏记录跳过，不毒化整个市场
            log.warning("skip bad record %s/%s: %s", market, rawrec.get("date"), e)
            continue
        if upsert_record(data_dir, rec):
            added += 1
    return added


def run_daily(data_dir="data"):
    changed = False
    core_failed = False
    for market in CORE_MARKETS:
        try:
            n = ingest_market(market, data_dir)
            changed = changed or n > 0
            log.info("core %s: +%d", market, n)
        except Exception as e:
            core_failed = True
            log.error("core market %s failed: %s", market, e)
    if core_failed:
        log.error("skipping extended markets because a core market failed")
        return changed, core_failed
    if EXTENDED_ENABLED:
        # 与回填同一条纪律：mkt 预检不过的扩展市场绝不落盘（防本地网络把各市场路由到 zh-CN feed）
        for market in verify_mkt(EXTENDED_MARKETS):
            try:
                n = ingest_market(market, data_dir)
                changed = changed or n > 0
            except Exception as e:
                log.warning("extended market %s failed (non-fatal): %s", market, e)
    write_aggregations(data_dir)
    return changed, core_failed


def main():
    parser = argparse.ArgumentParser(description="Bing 壁纸每日增量抓取")
    parser.add_argument("--data-dir", default="data")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    changed, core_failed = run_daily(data_dir=args.data_dir)
    log.info("changed=%s core_failed=%s", changed, core_failed)
    if core_failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
