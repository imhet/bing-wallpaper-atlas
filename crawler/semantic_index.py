"""语义索引构建：把每个图组的封面图编码成 512 维向量，按年份分片写入 data/sem/。

浏览器端加载向量后与查询向量做点积，即可跨语言/跨措辞检索——不依赖标签命中。
向量以 int8 存（每向量独立 scale），实测 6759 组下 top-20 与 fp32 重合 97.9%，
体积只有 fp32 的四分之一。

二进制格式（小端）：
  头部  magic b"BSEM" | version u8 | dim u16 | count u32
  条目  keylen u8 | key utf-8 | scale f32 | vec int8[dim]

key 与前端 api.js 的 recordKey() 同口径（imageKey 优先，否则去掉 CDN 市场后缀），
这样浏览器侧可以直接用已有记录查表，不需要额外的顺序文件。
"""

import json
import re
import struct
from pathlib import Path

MAGIC = b"BSEM"
VERSION = 1
DIM = 512
# 与 web/src/api.js 的 MARKET_PRIORITY 保持一致：同图多市场版本取中文视角记录
MARKET_PRIORITY = ("zh-cn", "en-us", "zh-tw")
_KEY_SUFFIX = re.compile(r"_[A-Z]{2}-[A-Z]{2}\d+$")


def record_key(rec):
    """图组键：镜像记录 urlbase 各市场不同路径，必须优先用 imageKey 归组。"""
    return rec.get("imageKey") or _KEY_SUFFIX.sub("", rec["urlbase"])


def _rank(rec):
    market = rec["market"]
    try:
        return (MARKET_PRIORITY.index(market), market)
    except ValueError:
        return (len(MARKET_PRIORITY), market)


def group_records(records):
    """按图组键归并，保留与前端 dedupeByUrlbase() 相同的代表记录。"""
    best = {}
    for rec in records:
        key = record_key(rec)
        if key not in best or _rank(rec) < _rank(best[key]):
            best[key] = rec
    return best


def quantize(vec):
    """对称 per-vector 量化，返回 (int8 列表, scale)。全零向量 scale 为 0。"""
    peak = max((abs(v) for v in vec), default=0.0)
    if peak == 0:
        return [0] * len(vec), 0.0
    scale = peak / 127
    return [max(-127, min(127, round(v / scale))) for v in vec], scale


def pack_shard(entries):
    """entries: [(key, int8 向量, scale), ...] → 分片字节。"""
    out = bytearray(MAGIC)
    out += struct.pack("<BHI", VERSION, DIM, len(entries))
    for key, vec, scale in entries:
        if len(vec) != DIM:
            raise ValueError(f"向量维度 {len(vec)} != {DIM}")
        kb = key.encode("utf-8")
        if len(kb) > 255:
            raise ValueError(f"key 过长（{len(kb)} 字节）：{key[:40]}")
        out += struct.pack("<B", len(kb)) + kb
        out += struct.pack("<f", scale)
        out += struct.pack(f"<{DIM}b", *vec)
    return bytes(out)


def unpack_shard(data):
    """分片字节 → [(key, int8 列表, scale), ...]。格式不符直接抛错，不做静默兜底。"""
    if data[:4] != MAGIC:
        raise ValueError("不是语义向量分片")
    version, dim, count = struct.unpack_from("<BHI", data, 4)
    if version != VERSION or dim != DIM:
        raise ValueError(f"版本/维度不支持：v{version} dim{dim}")
    pos = 11
    rows = []
    for _ in range(count):
        (klen,) = struct.unpack_from("<B", data, pos)
        pos += 1
        key = data[pos : pos + klen].decode("utf-8")
        pos += klen
        (scale,) = struct.unpack_from("<f", data, pos)
        pos += 4
        vec = list(struct.unpack_from(f"<{DIM}b", data, pos))
        pos += DIM
        rows.append((key, vec, scale))
    return rows


CONCEPT_MIN_COUNT = 5  # 频次低于此的标签太偏，当概念会把查询引向个别图片


def concept_vocab(records, min_count=CONCEPT_MIN_COUNT):
    """概念表 = 打标词表里出现 ≥min_count 次的词，按频次降序。

    这里只取 content_tags 的高频词做「查询 → 概念」的桥接索引，检索本身仍靠
    图向量，概念表不是检索依据——标签漏标、新词没进表都不影响图能不能被找到。
    """
    from collections import Counter

    counts = Counter(tag for rec in records for tag in (rec.get("content_tags") or []))
    return [word for word, n in counts.most_common() if n >= min_count]


def build_concepts(data_dir, out_dir, encode_clip_text, encode_bge):
    """概念表 → 两套对齐的 int8 分片（CLIP 侧给图打分，bge 侧给查询算权重）。

    两个文件的条目顺序必须完全一致：浏览器按下标把同一概念的两种向量配对。
    """
    from pathlib import Path

    words = concept_vocab(_load_records(data_dir))
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    clip_rows = [(w, *quantize(encode_clip_text(w))) for w in words]
    bge_rows = [(w, *quantize(encode_bge(w))) for w in words]
    (out_dir / "concepts_clip.bin").write_bytes(pack_shard(clip_rows))
    (out_dir / "concepts_bge.bin").write_bytes(pack_shard(bge_rows))
    return len(words)


def chinese_clip_encoder(model_name="OFA-Sys/chinese-clip-vit-base-patch16"):
    """Chinese-CLIP 图像塔编码器。返回 encode(rec) -> 归一化 512 维向量。

    Chinese-CLIP 的图文联合空间支持中文查询直连（「悬瀑」能落到瀑布图上），
    是这套索引能摆脱标签匹配的前提；换成别的视觉塔会丢掉中文语义对齐。
    """
    import io

    state = {}

    def encode(rec):
        import torch
        from PIL import Image
        from transformers import ChineseCLIPModel, ChineseCLIPProcessor

        from .content_tags import fetch_thumb

        # 惰性加载：没有新图时整个模型都不下载/不加载（每日 CI 常态）
        if not state:
            state["model"] = ChineseCLIPModel.from_pretrained(model_name).eval()
            state["proc"] = ChineseCLIPProcessor.from_pretrained(model_name)
        img = Image.open(io.BytesIO(fetch_thumb(rec["urlbase"]))).convert("RGB")
        with torch.no_grad():
            vec = state["model"].get_image_features(**state["proc"](images=[img], return_tensors="pt"))
        return (vec[0] / vec[0].norm()).tolist()

    return encode


def chinese_clip_text_encoder(model_name="OFA-Sys/chinese-clip-vit-base-patch16"):
    """Chinese-CLIP 文本塔：概念词 → 与图向量同一空间的 512 维归一化向量。"""
    state = {}

    def encode(text):
        import torch
        from transformers import ChineseCLIPModel, ChineseCLIPProcessor

        if not state:
            state["model"] = ChineseCLIPModel.from_pretrained(model_name).eval()
            state["proc"] = ChineseCLIPProcessor.from_pretrained(model_name)
        inputs = state["proc"](text=[text], return_tensors="pt", padding=True, truncation=True, max_length=52)
        with torch.no_grad():
            vec = state["model"].get_text_features(**inputs)
        return (vec[0] / vec[0].norm()).tolist()

    return encode


def bge_onnx_encoder(onnx_path, tokenizer_dir):
    """bge-small-zh int8 ONNX 编码器——与浏览器端必须是同一个 ONNX 文件。

    查询向量在浏览器里由这个模型算出，概念向量在构建期算出；两边用不同实现
    （PyTorch vs ONNX）会引入量化偏差，导致权重算出来和验证时不一致。
    """
    import numpy as np
    import onnxruntime as ort
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(tokenizer_dir)
    session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    input_names = {i.name for i in session.get_inputs()}

    def encode(text):
        batch = tokenizer([text], padding=True, truncation=True, max_length=64, return_tensors="np")
        feeds = {k: batch[k].astype("int64") for k in ("input_ids", "attention_mask", "token_type_ids") if k in input_names}
        hidden = session.run(None, feeds)[0][:, 0]
        return (hidden[0] / np.linalg.norm(hidden[0])).tolist()

    return encode


def _load_records(data_dir):
    recs = []
    for shard in sorted(Path(data_dir).glob("*/*.json")):
        if shard.parent.name == "sem":  # 输出目录也可能在 data 下
            continue
        recs.extend(json.loads(shard.read_text(encoding="utf-8")))
    return recs


def build(data_dir, out_dir, encode, limit=None):
    """增量构建：已索引的图组直接复用，只对新图组调用 encode(rec)。

    每天新增 1~2 张图时，不必重跑全量编码——这是 CI 每日任务能承受的前提。
    分片按年输出，年内条目按 key 排序，内容未变的年份不重写（保持 git diff 干净）。
    limit 限制本轮最多编码 N 张新图，多出的留待下次（试跑/分批用）。
    """
    data_dir, out_dir = Path(data_dir), Path(out_dir)
    groups = group_records(_load_records(data_dir))

    known = {}
    for path in sorted(out_dir.glob("*.bin")) if out_dir.exists() else []:
        for key, vec, scale in unpack_shard(path.read_bytes()):
            known[key] = (vec, scale)

    plan, stats = {}, {"added": 0, "reused": 0, "failed": 0}
    for key, rec in groups.items():
        if key in known:
            vec, scale = known[key]
            stats["reused"] += 1
        else:
            if limit is not None and stats["added"] >= limit:
                continue
            try:
                vec, scale = quantize(encode(rec))
            except Exception as e:  # 单张失败不拖垮整轮，下次运行幂等补上
                stats["failed"] += 1
                print(f"  ! {rec['id']}: {e}")
                continue
            stats["added"] += 1
        plan.setdefault(rec["date"][:4], []).append((key, vec, scale))

    out_dir.mkdir(parents=True, exist_ok=True)
    for year, entries in plan.items():
        blob = pack_shard(sorted(entries, key=lambda e: e[0]))
        path = out_dir / f"{year}.bin"
        if path.exists() and path.read_bytes() == blob:
            continue
        path.write_bytes(blob)
    return stats


def main():
    import argparse

    parser = argparse.ArgumentParser(description="语义索引：图组封面 → 512 维 int8 向量，按年分片")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--out-dir", default="data/sem")
    parser.add_argument("--model", default="OFA-Sys/chinese-clip-vit-base-patch16")
    parser.add_argument("--limit", type=int, default=0, help="最多编码 N 张新图（试跑用）")
    parser.add_argument("--concepts", action="store_true", help="重建概念向量（打标词表明显变化时才需要）")
    parser.add_argument("--bge-onnx", default="", help="bge-small-zh int8 ONNX 路径（--concepts 必填）")
    parser.add_argument("--bge-tokenizer", default="", help="bge tokenizer 目录（--concepts 必填）")
    args = parser.parse_args()

    if args.concepts:
        n = build_concepts(
            args.data_dir,
            args.out_dir,
            chinese_clip_text_encoder(args.model),
            bge_onnx_encoder(args.bge_onnx, args.bge_tokenizer),
        )
        print(f"sem concepts: {n} 个")
        return

    stats = build(args.data_dir, args.out_dir, chinese_clip_encoder(args.model), limit=args.limit or None)
    print(f"sem: {stats['added']} added, {stats['reused']} reused, {stats['failed']} failed")


if __name__ == "__main__":
    main()
