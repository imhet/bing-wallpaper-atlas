"""部署后主动刷新 jsDelivr 缓存。

前端数据文件走 jsDelivr 分流（api.js 的 fetchJSON），@main 有最长 12h 缓存：
每日更新 push 后不 purge，国内用户最长半天读到旧分片。只 purge 会变的数据文件
（聚合、分片、语义向量、词典）；缩略图 webp 不在列——数量大易撞 purge 频率限制，
且只随 backfill 增长、每日更新不触碰。

用法：python -m crawler.purge_jsdelivr --data-dir data
失败不抛异常退出码非零即可：workflow 里 continue-on-error，purge 失败只意味
回退到 12h 自然过期，不该红灯整个部署。
"""

import argparse
import sys
import time
from pathlib import Path

import requests

REPO = "imhet/bing-wallpaper-atlas"
PURGE_URL = "https://purge.jsdelivr.net/gh/" + REPO + "@main/{path}"
RETRIES = 3
INTERVAL = 0.3  # purge 接口有频率限制，逐文件小间隔


def collect_paths(data_dir: Path) -> list[str]:
    """purge 清单：aggregations + 各市场分片 + 语义向量 + 词典（web/public/data 同名文件）。"""
    paths = ["data/aggregations.json", "data/geo_aliases.json"]
    for shard in sorted(data_dir.glob("*/*.json")):
        paths.append("data/" + shard.relative_to(data_dir).as_posix())
    for bin_file in sorted((data_dir / "sem").glob("*.bin")):
        paths.append("data/sem/" + bin_file.name)
    return paths


def purge(paths: list[str], session) -> tuple[int, int]:
    """逐文件 purge，返回 (成功数, 失败数)。网络异常与 5xx 一律重试。"""
    ok = fail = 0
    for path in paths:
        url = PURGE_URL.format(path=path)
        for attempt in range(RETRIES):
            try:
                if session.get(url, timeout=15).ok:
                    ok += 1
                    break
            except requests.RequestException:
                pass
            if attempt == RETRIES - 1:
                fail += 1
                print(f"::warning::purge 失败（已重试 {RETRIES} 次）：{path}")
            else:
                time.sleep(1)
        time.sleep(INTERVAL)
    return ok, fail


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="data")
    args = parser.parse_args()
    paths = collect_paths(Path(args.data_dir))
    print(f"purge {len(paths)} 个文件 ...")
    ok, fail = purge(paths, requests.Session())
    print(f"{ok} 成功，{fail} 失败")
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
