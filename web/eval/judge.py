"""池化判定：给每条查询的候选池打相关性（0/1/2），补齐评估集。

锚点是人工规则确定的真值，固定 2 分，不交给模型；其余候选（检索前 20）由
LLM 判定。这样 nDCG 的分母覆盖了用户实际会看到的结果，而不是只对 30 条锚点
算分——只判锚点会把「用户看到但没判过」的相关结果误当成不相关。

用法：./.venv/bin/python web/eval/judge.py [--fresh]
输出：web/eval/judgments.json（支持断点续跑，已判定的查询跳过）
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MODEL = "deepseek-flash"
BATCH = 8
WORKERS = 4

PROMPT = """你是图库检索评估员。用户查询：{q}

判断下列每张壁纸与查询的相关程度。输出一个 JSON 对象：键是每行开头的记录 id（原样抄写），值是整数 0/1/2。只输出 JSON，不要解释。
评分标准：
2 = 完全符合：画面主体就是查询所指的事物
1 = 部分相关：画面包含该事物但非主体，或概念接近可接受
0 = 不相关
示例格式（键是真实记录 id，不是 "id" 这个单词）：{{"zh-cn-2023-10-05": 2, "en-us-2024-01-01": 0}}

候选：
{items}
"""


def load_records():
    by_id = {}
    for f in sorted((ROOT / "data").glob("*/*.json")):
        if f.parent.name == "thumbs":
            continue
        for r in json.loads(f.read_text(encoding="utf-8")):
            by_id[r["id"]] = r
    return by_id


def call_llm(prompt, retries=3):
    url = os.environ["ANTHROPIC_BASE_URL"].rstrip("/") + "/v1/messages"
    body = json.dumps({
        "model": MODEL,
        "max_tokens": 4096,
        "temperature": 0,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    for i in range(retries):
        req = urllib.request.Request(url, data=body, headers={
            "content-type": "application/json",
            "authorization": f"Bearer {os.environ['ANTHROPIC_AUTH_TOKEN']}",
            "x-api-key": os.environ["ANTHROPIC_AUTH_TOKEN"],
            "anthropic-version": "2023-06-01",
        })
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.load(resp)
            return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        except Exception as e:  # 429/超时都重试，最终失败由调用方跳过
            if i == retries - 1:
                print(f"  ! 调用失败: {type(e).__name__} {e}", file=sys.stderr)
                return None
            time.sleep(4 * (i + 1))
    return None


def parse_json(text):
    if not text:
        return {}
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return {}
    try:
        raw = json.loads(m.group())
    except ValueError:
        return {}
    return {k: v for k, v in raw.items() if isinstance(v, int) and 0 <= v <= 2}


def describe(r):
    tags = ",".join((r.get("content_tags") or [])[:10])
    loc = ", ".join((r.get("location") or [])[:2])
    desc = (r.get("desc") or "").strip()[:160]
    return f"{r['id']}: 标题={r.get('title') or '(空)'} | 地点={loc or '-'} | 画面={tags or '-'} | 描述={desc or '-'}"


def judge_query(item, by_id):
    anchors = set(item["anchors"])
    todo = [i for i in item["candidates"] if i not in anchors]
    scores = {i: 2 for i in anchors if i in by_id}
    for start in range(0, len(todo), BATCH):
        batch = [i for i in todo[start:start + BATCH] if i in by_id]
        if not batch:
            continue
        prompt = PROMPT.format(q=item["query"], items="\n".join(describe(by_id[i]) for i in batch))
        got = parse_json(call_llm(prompt))
        for i in batch:
            if i in got:  # 只认候选里的真实 id，模型的占位键一律丢弃
                scores[i] = got[i]
    return item["query"], scores


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fresh", action="store_true", help="忽略已有结果重新判定")
    args = ap.parse_args()

    candidates = json.loads((HERE / "candidates.json").read_text(encoding="utf-8"))
    by_id = load_records()
    out_path = HERE / "judgments.json"
    done = {} if args.fresh or not out_path.exists() else json.loads(out_path.read_text(encoding="utf-8"))

    pending = [c for c in candidates if c["query"] not in done]
    print(f"待判定 {len(pending)} / {len(candidates)} 条查询")

    with ThreadPoolExecutor(WORKERS) as pool:
        futures = [pool.submit(judge_query, item, by_id) for item in pending]
        for n, fut in enumerate(futures, 1):
            q, scores = fut.result()
            done[q] = scores
            if n % 10 == 0 or n == len(futures):
                out_path.write_text(json.dumps(done, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
                print(f"  完成 {n}/{len(futures)}")

    out_path.write_text(json.dumps(done, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    total = sum(len(v) for v in done.values())
    judged = sum(1 for v in done.values() for s in v.values() if s > 0)
    print(f"判定完成：{len(done)} 条查询，{total} 个判定，其中相关 {judged} 个")


if __name__ == "__main__":
    main()
