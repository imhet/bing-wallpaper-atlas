"""深史镜像缩略图生成：npanuhin 镜像原图（74~339KB、Cloudflare 无边缘缓存）直接当网格
缩略图加载太慢，这里预生成 480 宽 WebP（12~27KB）供前端 thumbUrl 使用。

深史已封顶（END_DATE=2021-02-01）不再增长，属一次性任务：缩略图不进 git
（.gitignore 的 data/thumbs/），线上由 daily.yml 的 actions/cache 生成并随 Pages 分发。
"""

import argparse
import io
import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

THUMB_WIDTH = 480
QUALITY = 72
WORKERS = 8
MIRROR_PREFIX = "https://"


def thumb_path(data_dir, rec):
    return Path(data_dir) / "thumbs" / rec["market"] / rec["date"][:4] / f"{rec['date']}.webp"


def mirror_records(data_dir):
    for shard in sorted(Path(data_dir).glob("*/*.json")):
        for rec in json.loads(shard.read_text()):
            if rec.get("urlbase", "").startswith(MIRROR_PREFIX):
                yield rec


def _default_fetch(url):
    with urllib.request.urlopen(url, timeout=30) as resp:
        return resp.read()


def _make_thumb(rec, path, fetch):
    img = Image.open(io.BytesIO(fetch(rec["urlbase"]))).convert("RGB")
    size = (THUMB_WIDTH, round(img.height * THUMB_WIDTH / img.width))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.resize(size, Image.LANCZOS).save(path, format="WEBP", quality=QUALITY, method=6)


def generate(data_dir, limit=None, fetch=None, workers=WORKERS):
    fetch = fetch or _default_fetch
    stats = {"done": 0, "skipped": 0, "failed": 0}
    todo = []
    for rec in mirror_records(data_dir):
        if thumb_path(data_dir, rec).exists():
            stats["skipped"] += 1
        else:
            todo.append(rec)
    if limit is not None:
        todo = todo[:limit]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_make_thumb, rec, thumb_path(data_dir, rec), fetch): rec for rec in todo}
        for fut, rec in futs.items():
            try:
                fut.result()
                stats["done"] += 1
            except Exception as e:  # 单张失败只跳过——重跑幂等补上
                stats["failed"] += 1
                print(f"  ! {rec['id']}: {e}")
    return stats


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--limit", type=int, default=None, help="最多生成 N 张（试跑用）")
    args = ap.parse_args()
    stats = generate(args.data_dir, limit=args.limit)
    print(f"thumbs: {stats['done']} generated, {stats['skipped']} skipped, {stats['failed']} failed")


if __name__ == "__main__":
    main()
