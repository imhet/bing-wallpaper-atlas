"""CLIP 零样本内容打标：给每张图生成「图中内容」标签（雪山/兔子/极光…）。

动机：壁纸的文字描述极少写画面内容——语料含「雪」字仅 26 条、搜「雪山」零召回。
手机相册式的图片理解搜索。标签写入记录的 content_tags 字段（区别于 geo_enrich
的地点 tags），前端把它加进搜索字段并展示。

推理：open_clip ViT-B-32（CPU 即可），缩略图 400x240 从 Bing CDN 拉到内存、
用完即弃（图片永不落地原则不变——仓库里只有标签文字）。
词表见 content_vocab.json：{zh, en}，en 参与 CLIP 文本塔，zh 进 tags。
"""

import argparse
import io
import json
import logging
from pathlib import Path

import requests

from .storage import load_all, upsert_record

VOCAB_PATH = Path(__file__).parent / "content_vocab.json"
MODEL_NAME = "ViT-B-32"
PRETRAINED = "laion2b_s34b_b79k"
TOP_K = 5
RATIO = 0.35  # 相对阈值：得分 < max*RATIO 的概念丢弃（CLIP 分数分布平，绝对阈值不稳）
THUMB_SUFFIX = "_400x240.jpg"
BING_BASE = "https://www.bing.com"

log = logging.getLogger(__name__)

_state = {}  # 进程级单例：model/preprocess/tokenizer/text_emb/vocab


def _load_vocab():
    return json.loads(VOCAB_PATH.read_text(encoding="utf-8"))


def _init():
    if _state:
        return _state
    import open_clip
    import torch

    model, _, preprocess = open_clip.create_model_and_transforms(MODEL_NAME, pretrained=PRETRAINED)
    tokenizer = open_clip.get_tokenizer(MODEL_NAME)
    model.eval()
    vocab = _load_vocab()
    prompts = torch.cat([tokenizer(f"a photo of {v['en']}") for v in vocab])
    with torch.no_grad():
        text_emb = model.encode_text(prompts)
        text_emb /= text_emb.norm(dim=-1, keepdim=True)
    _state.update(model=model, preprocess=preprocess, text_emb=text_emb, vocab=vocab)
    return _state


def tag_image(image_bytes):
    """单张图片字节 → 内容标签列表（zh）。"""
    import torch
    from PIL import Image

    s = _init()
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    with torch.no_grad():
        emb = s["model"].encode_image(s["preprocess"](img).unsqueeze(0))
        emb /= emb.norm(dim=-1, keepdim=True)
        scores = (emb @ s["text_emb"].T).squeeze(0)
    top = scores.topk(TOP_K)
    cutoff = top.values[0].item() * RATIO
    return [s["vocab"][i]["zh"] for v, i in zip(top.values, top.indices) if v.item() >= cutoff]


def fetch_thumb(urlbase):
    resp = requests.get(f"{BING_BASE}{urlbase}{THUMB_SUFFIX}", timeout=20)
    resp.raise_for_status()
    return resp.content


def main():
    parser = argparse.ArgumentParser(description="CLIP 内容打标")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--limit", type=int, default=0, help="最多处理 N 张唯一图（0=全部）")
    parser.add_argument("--ids", default="", help="逗号分隔的记录 id，只处理这些所在图组")
    parser.add_argument("--dry-run", action="store_true", help="只打印不写库")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    wanted = set(filter(None, args.ids.split(",")))
    # 同一天全球各市场发同一张图：按 imageKey 分组，每组只推理一次、标签写组内全部记录
    # （详情页切任意市场版本都能看到画面标签；imageKey 为 null 的记录按 id 独立成组）
    groups = {}
    for market, recs in sorted(load_all(args.data_dir).items()):
        for rec in recs:
            groups.setdefault(rec.get("imageKey") or f"id:{rec['id']}", []).append(rec)

    done = 0
    for key, recs in groups.items():
        if wanted and not {r["id"] for r in recs} & wanted:
            continue
        if not wanted and any(r.get("content_tags") for r in recs):
            continue  # 该图已打标（增量语义）
        lead = recs[0]
        try:
            tags = tag_image(fetch_thumb(lead["urlbase"]))
        except Exception as e:
            log.warning("skip group %s: %s", key, e)
            continue
        print(f"{key} | {lead['date']} {(lead.get('desc') or '')[:36]} → {tags} ({len(recs)}条)")
        if not args.dry_run:
            for rec in recs:
                upsert_record(args.data_dir, {**rec, "content_tags": tags})
        done += 1
        if args.limit and done >= args.limit:
            log.info("达到 --limit=%d，停止", args.limit)
            return
    log.info("content tagging done: %d 张唯一图%s", done, "（dry-run 未写库）" if args.dry_run else "")


if __name__ == "__main__":
    main()
