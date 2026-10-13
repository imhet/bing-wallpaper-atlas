"""内容打标：给每张图生成「图中内容」标签（雪山/兔子/乐山大佛…）。

动机：壁纸的文字描述极少写画面内容——语料含「雪」字仅 26 条、搜「雪山」零召回。
手机相册式的图片理解搜索。标签写入记录的 content_tags 字段（区别于 geo_enrich
的地点 tags），前端把它加进搜索字段并展示。

双引擎：VLM（glm-5.3-flash，开放理解，认得出「乐山大佛」这类专名和词表外概念）
优先，凭证取环境变量 ANTHROPIC_BASE_URL / ANTHROPIC_AUTH_TOKEN；未配置或调用
失败自动降级本地 CLIP（open_clip ViT-B-16，词表 content_vocab.json 闭集分类）。
缩略图 400x240 从 Bing CDN 拉到内存、用完即弃（图片永不落地原则不变——仓库里
只有标签文字）。
"""

import argparse
import base64
import io
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

from .storage import load_all, upsert_record

VOCAB_PATH = Path(__file__).parent / "content_vocab.json"
MODEL_NAME = "ViT-B-16"
PRETRAINED = "laion2b_s34b_b88k"
TOP_K = 3
RATIO = 0.5  # 相对阈值：得分 < max*RATIO 的概念丢弃（ViT-B-16 上近邻比值实测 ~0.6-0.7，
# 正确第二概念 ~0.8+；0.5 砍掉猴子/山羊类形状近邻，留下真第二主体）
THUMB_SUFFIX = "_400x240.jpg"
BING_BASE = "https://www.bing.com"

VLM_MODEL = "glm-5.3-flash"
VLM_MAX_TAGS = 6
VLM_PROMPT = (
    "看这张壁纸图片，输出画面里的主要内容实体，用简体中文标签的 JSON 数组，只输出 JSON。"
    "标签要具体：动物到物种、建筑到类型，知名地标输出通用中文名（如「乐山大佛」）；"
    "不要情绪氛围词（宁静/壮丽），不要品牌或水印文字；最多 6 个，按显著程度排序。"
)

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


def _parse_vlm_tags(text):
    """从模型回复中提取 JSON 标签数组。

    返回 None = 无有效 JSON（调用方降级 CLIP）；返回 [] = VLM 明确判断图中
    无可标注实体（合法结论，绝不能降级 CLIP 硬凑词表标签）。
    """
    if not text:
        return None
    try:
        items = json.loads(text.strip())
    except ValueError:
        items = None
    if items is None:
        m = re.search(r"\[.*\]", text, re.DOTALL)
        if not m:
            return None
        try:
            items = json.loads(m.group())
        except ValueError:
            return None
    if not isinstance(items, list):
        return None
    return [t.strip() for t in items if isinstance(t, str) and t.strip()][:VLM_MAX_TAGS]


def vlm_tag_image(image_bytes):
    """单张图片字节 → VLM 内容标签列表（可为 [] = 图中无可标注实体）；无有效 JSON 时抛 ValueError。"""
    body = {
        "model": VLM_MODEL,
        "max_tokens": 1024,  # thinking 块也计入输出配额，400 会在 JSON 中途截断
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                             "data": base64.standard_b64encode(image_bytes).decode()}},
                {"type": "text", "text": VLM_PROMPT},
            ],
        }],
    }
    req = urllib.request.Request(
        f"{os.environ['ANTHROPIC_BASE_URL']}/v1/messages",
        data=json.dumps(body).encode(),
        headers={
            "content-type": "application/json",
            "authorization": f"Bearer {os.environ['ANTHROPIC_AUTH_TOKEN']}",
            "x-api-key": os.environ["ANTHROPIC_AUTH_TOKEN"],
            "anthropic-version": "2023-06-01",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        out = json.load(resp)
    text = "".join(b.get("text", "") for b in out.get("content", []) if b.get("type") == "text")
    tags = _parse_vlm_tags(text)
    if tags is None:
        raise ValueError(f"VLM 回复无有效标签: {text[:80]}")
    return tags


def _shrink_image(image_bytes, max_width=640):
    """镜像原图缩到 max_width 宽（VLM 按图片像素计 token，1920 原图约为 640 的 9 倍开销）。"""
    from PIL import Image

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    if img.width <= max_width:
        return image_bytes
    h = round(img.height * max_width / img.width)
    buf = io.BytesIO()
    img.resize((max_width, h)).save(buf, "JPEG", quality=85)
    return buf.getvalue()


def fetch_thumb(urlbase):
    if urlbase.startswith("https://"):
        # 镜像绝对 URL（npanuhin 深史）：无 _400x240 档，拉原图后本地缩
        resp = requests.get(urlbase, timeout=30)
        resp.raise_for_status()
        return _shrink_image(resp.content)
    resp = requests.get(f"{BING_BASE}{urlbase}{THUMB_SUFFIX}", timeout=20)
    resp.raise_for_status()
    return resp.content


def main():
    parser = argparse.ArgumentParser(description="内容打标（VLM 优先，降级 CLIP）")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--limit", type=int, default=0, help="最多处理 N 张唯一图（0=全部）")
    parser.add_argument("--ids", default="", help="逗号分隔的记录 id，只处理这些所在图组")
    parser.add_argument(
        "--force",
        action="store_true",
        help="忽略增量语义（已打标跳过），全部图组重打——词表/阈值/模型更新后使用",
    )
    parser.add_argument("--engine", choices=["vlm", "clip"], default="vlm",
                        help="vlm=VLM 优先失败降级 CLIP（默认）；clip=纯本地")
    parser.add_argument("--workers", type=int, default=1, help="并发推理线程数（写回始终串行）")
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

    todo = []
    for key, recs in groups.items():
        if wanted and not {r["id"] for r in recs} & wanted:
            continue
        # 增量语义：content_tags is not None（含 [] = VLM 判断无可标注实体）即视为已打标
        if not wanted and not args.force and any(r.get("content_tags") is not None for r in recs):
            continue
        todo.append((key, recs))
        if args.limit and len(todo) >= args.limit:
            break

    def infer(item):
        key, recs = item
        lead = recs[0]
        try:
            img = fetch_thumb(lead["urlbase"])
        except Exception as e:  # 拉图失败只跳过该组（增量语义下轮重跑自动补打），不能崩全进程
            log.warning("图拉取失败，跳过: %s: %s", key, e)
            return None
        if args.engine == "vlm":
            # 429 指数退避三次（编码套餐限流紧，退避自适应节奏）；耗尽后跳过不降级——
            # 限流是暂时不可用而非「VLM 判不了」，降级 CLIP 会混入词表风格标签
            # （2026-10-13 实证：单日 38% 降级污染），增量语义下轮自动补打。
            # 其他错误（解析失败等）重试一次后仍降级 CLIP 兜底。
            delays = (2, 5, 10) if args.engine == "vlm" else ()
            for attempt, wait in enumerate((*delays, 0)):
                try:
                    return key, recs, vlm_tag_image(img)
                except urllib.error.HTTPError as e:
                    if e.code == 429 and wait:
                        time.sleep(wait)
                        continue
                    if e.code == 429:
                        log.warning("429 退避耗尽，跳过（下轮补打）: %s", key)
                        return None
                    log.warning("VLM HTTP %s，降级 CLIP: %s", e.code, key)
                    break
                except Exception as e:
                    if wait:
                        time.sleep(2)
                        continue
                    log.warning("VLM 失败，降级 CLIP: %s: %s", key, e)
                    break
        return key, recs, tag_image(img)

    # 推理并发、写回串行：upsert 是整分片读改写，并发写会互相覆盖
    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for result in ex.map(infer, todo):
            if result is None:  # 拉图失败的组
                continue
            key, recs, tags = result
            print(f"{key} | {recs[0]['date']} {(recs[0].get('desc') or '')[:36]} → {tags} ({len(recs)}条)")
            if not args.dry_run:
                for rec in recs:
                    upsert_record(args.data_dir, {**rec, "content_tags": tags})
            done += 1
    log.info("content tagging done: %d 张唯一图%s", done, "（dry-run 未写库）" if args.dry_run else "")


if __name__ == "__main__":
    main()
