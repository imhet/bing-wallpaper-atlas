"""图片直链健康巡检。

站点的全部资产是元数据 + 直链——Bing CDN 老图链接没有任何 SLA，直链大规模
失效时必须第一时间红灯，而不是等用户发现图全灰。每日 workflow 分层采样
（每个 市场×年份 至少 2 条，再随机补足），HEAD 探测 fhd 档 / 镜像原图。

退出码：0 健康；1 死链率超阈值；2 未知率过高（网络不可信，结果无意义）。
探测三态语义与 resolutions.py 一致：False=确认死链，None=网络失败（重试一次，
仍失败计入 unknown，不算死链——CI 网络抖动不该误报 CDN 大屠杀）。

用法：python -m crawler.link_check --data-dir data [--sample 200]
"""

import argparse
import json
import random
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

from crawler.resolutions import BASE, _probe

PER_GROUP_MIN = 2
FAIL_THRESHOLD = 0.02  # 死链率超过 2% 红灯（采样 200 条即 ≥4 条死链）
UNKNOWN_THRESHOLD = 0.2  # 网络级失败超过 20% 视为探测本身不可信
PROBE_WORKERS = 4


def sample_records(data_dir: Path, sample: int, random=random) -> list[dict]:
    """分层采样：每个 (market, year) 保底 PER_GROUP_MIN 条，再随机补足到 sample 条。

    保底是为了老图——死链风险集中在 2010 年代的镜像深史，纯随机采样对它们覆盖不足。
    """
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for shard in sorted(data_dir.glob("*/*.json")):
        for r in json.loads(shard.read_text(encoding="utf-8")):
            groups[(r["market"], r["date"][:4])].append(r)
    picked, picked_ids = [], set()
    for key in sorted(groups):
        for r in random.sample(groups[key], min(PER_GROUP_MIN, len(groups[key]))):
            picked.append(r)
            picked_ids.add(r["id"])
    rest = [r for rs in groups.values() for r in rs if r["id"] not in picked_ids]
    picked.extend(random.sample(rest, min(len(rest), max(0, sample - len(picked)))))
    return picked


def probe_url(r: dict) -> str:
    """Bing 记录探 fhd 档（全站详情页默认档），镜像记录直探原图。"""
    if r["urlbase"].startswith("https://"):
        return r["urlbase"]
    return f"{BASE}{r['urlbase']}_1920x1080.jpg"


def probe_urls(records: list[dict], session) -> list[dict]:
    """并发探测，返回 [{id, url, ok}]，ok ∈ {True, False, None}（None=网络失败）。"""
    jobs = [(r["id"], probe_url(r)) for r in records]

    def run(job):
        rid, url = job
        ok = _probe(url, session)
        if ok is None:
            ok = _probe(url, session)  # 网络失败重试一次再计入 unknown
        return {"id": rid, "url": url, "ok": ok}

    with ThreadPoolExecutor(max_workers=PROBE_WORKERS) as ex:
        return list(ex.map(run, jobs))


def evaluate(dead: int, probed: int, unknown: int, threshold: float = FAIL_THRESHOLD, unknown_threshold: float = UNKNOWN_THRESHOLD) -> tuple[int, str]:
    if probed and unknown / (probed + unknown) > unknown_threshold:
        return 2, f"{unknown}/{probed + unknown} unknown ({unknown / (probed + unknown):.1%})"
    rate = dead / probed if probed else 0
    detail = f"{dead}/{probed} ({rate:.1%})"
    return (1, detail) if probed and rate > threshold else (0, detail)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--sample", type=int, default=200)
    args = parser.parse_args()
    records = sample_records(Path(args.data_dir), args.sample)
    print(f"采样 {len(records)} 条直链探测中 ...")
    results = probe_urls(records, requests.Session())
    dead = [r for r in results if r["ok"] is False]
    unknown = [r for r in results if r["ok"] is None]
    for r in dead:
        print(f"DEAD {r['id']} {r['url']}")
    code, detail = evaluate(len(dead), len(results) - len(unknown), len(unknown))
    print(f"死链 {detail}，未知 {len(unknown)}")
    sys.exit(code)


if __name__ == "__main__":
    main()
