"""图组显式化：存量记录补 imageKey（含 npanuhin 镜像记录的 bing_url 桥接）。

老记录 imageKey 为 null，打标时按市场各自成组——VLM 生成式输出措辞随机
（同图跨市场打出「黄色民居外墙/黄墙建筑/黄色房屋」），重复推理还浪费配额。
回填后 content_tags 按图组收敛：一组只推理一次、标签写组内全部记录。

geo 地名 tags 不做组并集：tags 由各市场文案派生，长文里的顺带提及（如过山车历史
提到巴黎/德国）会被并集扩散到全组，造成搜索误挂。content_tags 才是需要组级一致的部分。
"""

import argparse
import logging
import re

import requests

from .image_key import extract_image_key
from .storage import load_all, upsert_record

log = logging.getLogger(__name__)

_BING_URL_RE = re.compile(r"OHR\.([A-Za-z0-9]+?)_[A-Z]{2}-[A-Z]{2}")
_MIRROR_URL_RE = re.compile(r"bing\.npanuhin\.me/([A-Za-z]{2})/([a-z]{2})/")


def parse_bing_url_image_key(bing_url):
    """npanuhin 的 bing_url（OHR.X_DE-DE123_UHD.jpg）→ OHR 图组键；无 OHR ID 返回 None。"""
    if not bing_url:
        return None
    m = _BING_URL_RE.search(bing_url)
    return m.group(1) if m else None


def mirror_slug(urlbase):
    """镜像绝对 URL → npanuhin slug（/DE/de/ → DE-de）；非镜像返回 None。"""
    if not urlbase:
        return None
    m = _MIRROR_URL_RE.search(urlbase)
    return f"{m.group(1)}-{m.group(2)}" if m else None


def build_mirror_mapping(data_dir="data"):
    """拉 npanuhin 各市场 JSON，建 {(slug, date): OHR图组键} 映射；失败的市场跳过不阻塞。"""
    mapping = {}
    slugs = sorted({s for recs in load_all(data_dir).values() for r in recs if (s := mirror_slug(r.get("urlbase")))})
    for slug in slugs:
        try:
            resp = requests.get(f"https://bing.npanuhin.me/{slug}.json", timeout=30)
            resp.raise_for_status()
        except Exception as e:
            log.warning("npanuhin %s 拉取失败，该市场镜像记录跳过回填: %s", slug, e)
            continue
        for item in resp.json():
            key = parse_bing_url_image_key(item.get("bing_url"))
            if key:
                mapping[(slug, item["date"])] = key
    return mapping


def backfill_mirror_image_keys(records, mapping):
    """镜像记录按 (slug, date) 从 bing_url 映射回填 imageKey；Bing 相对路径与映射缺失的记录不动。"""
    out = []
    for r in records:
        key = None
        if not r.get("imageKey"):
            slug = mirror_slug(r.get("urlbase"))
            if slug:
                key = mapping.get((slug, r["date"]))
        out.append({**r, "imageKey": key} if key else r)
    return out


def group_key(rec):
    """图组键：imageKey → urlbase 归一 → id（镜像深史单市场无重复，id 兜底安全）。"""
    return rec.get("imageKey") or extract_image_key(rec.get("urlbase") or "") or f"id:{rec['id']}"


def backfill_image_keys(records):
    """imageKey 为 null 的记录从 urlbase 归一补齐；镜像绝对 URL 无 OHR ID 保持 null。"""
    return [{**r, "imageKey": r.get("imageKey") or extract_image_key(r.get("urlbase") or "")} for r in records]


def main(argv=None):
    parser = argparse.ArgumentParser(description="存量记录补 imageKey（含 npanuhin 镜像桥接）")
    parser.add_argument("--data-dir", default="data")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    flat = [r for _, recs in sorted(load_all(args.data_dir).items()) for r in recs]
    mirror_mapping = build_mirror_mapping(args.data_dir)
    log.info("npanuhin bing_url 映射 %d 条", len(mirror_mapping))
    filled = backfill_mirror_image_keys(backfill_image_keys(flat), mirror_mapping)

    changed = n_filled = 0
    for old, new in zip(flat, filled):  # backfill 严格保序，zip 对位成立
        if not old.get("imageKey") and new.get("imageKey"):
            n_filled += 1
        if old != new and upsert_record(args.data_dir, new):
            changed += 1
    n_groups = len({group_key(r) for r in filled})
    log.info(
        "group align done: imageKey 回填 %d 条，唯一图组 %d 个，变更写回 %d 条",
        n_filled, n_groups, changed,
    )


if __name__ == "__main__":
    main()
