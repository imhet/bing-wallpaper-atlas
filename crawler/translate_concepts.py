#!/usr/bin/env python3
"""概念表双语：把 data/sem/concepts_bge.bin 里的中文概念词翻成英文画面标签。

产出 data/sem/concepts_en.json：字符串数组，下标与 concepts_clip.bin / concepts_bge.bin
严格对齐（浏览器端语义检索的英文查询走词面匹配，不重编 6770 张图的向量）。
幂等可续跑：输出文件里已有的条目直接跳过，只补缺失/空位。

凭证与 content_tags.py 同源：环境变量 ANTHROPIC_BASE_URL / ANTHROPIC_AUTH_TOKEN，
模型默认 glm-4-flash（免费档），TRANSLATE_MODEL 可覆盖。
"""

import json
import os
import re
import struct
import sys
import time
import urllib.request

BATCH = 64
PROMPT = (
    "把下面的中文画面标签逐个翻译成英文。每个词输出一个字符串，格式是「主标签, 同义词2, 同义词3」——"
    "主标签是最常用的英文画面标签，后面跟 1~2 个用户可能会搜的同义/近义英文写法，全部小写，"
    "用英文逗号分隔。示例：输入「雪山」输出 \"snowy mountain, snow-capped peak, snow mountain\"；"
    "输入「晚霞」输出 \"sunset glow, dusk sky, evening glow\"。"
    "只输出 JSON 数组，数组长度必须与输入条数一致，不要解释。输入：\n{words}"
)


def load_concepts(path):
    """读 BSEM 分片的词表（顺序即向量下标）。格式见 semantic_index.py。"""
    raw = open(path, "rb").read()
    magic, ver, dim, count = struct.unpack_from("<4sBHI", raw, 0)
    assert magic == b"BSEM", f"{path} 不是概念向量分片"
    assert ver == 1, f"分片版本不支持: v{ver}"
    off = 11
    words = []
    for _ in range(count):
        kl = raw[off]
        off += 1
        words.append(raw[off : off + kl].decode("utf-8"))
        off += kl + 4 + dim
    assert off == len(raw), "分片长度不齐"
    return words


def sanitize(en):
    """清掉模型偶尔回显的原中文词；整条无英文的返回空串（由续跑重翻）。"""
    import re

    cleaned = re.sub(r"[^ -~]+", "", en).strip(" ,")
    return re.sub(r"(?:\s*,\s*)+", ", ", cleaned) if cleaned else ""


def translate_batch(words, model):
    """一批中文词 → 等长英文标签数组；解析失败/长度不符抛 ValueError。"""
    body = {
        "model": model,
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": PROMPT.format(words=json.dumps(words, ensure_ascii=False))}],
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
    with urllib.request.urlopen(req, timeout=120) as resp:
        out = json.load(resp)
    text = "".join(b.get("text", "") for b in out.get("content", []) if b.get("type") == "text")
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if not m:
        raise ValueError(f"回复无 JSON 数组: {text[:120]}")
    items = json.loads(m.group())
    if not isinstance(items, list) or len(items) != len(words):
        raise ValueError(f"长度不符: 期望 {len(words)} 得 {len(items) if isinstance(items, list) else type(items)}")
    return [str(x).strip() for x in items]


def merge(existing, translated, total):
    """已翻译的保留、缺失位补 None → 供续跑判断。"""
    out = list(existing) if existing else []
    out.extend([None] * (total - len(out)))
    for i, en in enumerate(translated):
        if en:
            out[i] = en
    return out


def main():
    data_dir = sys.argv[sys.argv.index("--data-dir") + 1] if "--data-dir" in sys.argv else "data"
    src = os.path.join(data_dir, "sem", "concepts_bge.bin")
    dst = os.path.join(data_dir, "sem", "concepts_en.json")
    words = load_concepts(src)
    done = []
    if os.path.exists(dst):
        with open(dst, encoding="utf-8") as f:
            done = json.load(f)
    table = merge(done, [], len(words))
    table = [sanitize(en) or None if en else None for en in table]
    model = os.environ.get("TRANSLATE_MODEL") or "glm-4-flash"
    pending = [i for i, en in enumerate(table) if not en]
    print(f"概念 {len(words)} 个，待翻译 {len(pending)} 个，模型 {model}")
    for start in range(0, len(pending), BATCH):
        idx = pending[start : start + BATCH]
        batch_words = [words[i] for i in idx]
        for attempt in range(3):
            try:
                en = translate_batch(batch_words, model)
                break
            except (ValueError, OSError, KeyError) as e:
                print(f"  批 {start // BATCH + 1} 第 {attempt + 1} 次失败: {e}", file=sys.stderr)
                time.sleep(2 * (attempt + 1))
        else:
            print(f"  批 {start // BATCH + 1} 三次失败，跳过该批（续跑再补）", file=sys.stderr)
            continue
        for i, s in zip(idx, en):
            table[i] = sanitize(s) or None
        with open(dst, "w", encoding="utf-8") as f:
            json.dump(table, f, ensure_ascii=False, indent=0)
        print(f"  批 {start // BATCH + 1}: {len(idx)} 个完成 → {dst}")
    missing = sum(1 for en in table if not en)
    print(f"完成，缺 {missing} 个" + ("（重跑本脚本续补）" if missing else ""))


if __name__ == "__main__":
    main()
