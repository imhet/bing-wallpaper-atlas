"""生成 web/eval/queries.json：100 条查询 + 锚点（人工确认的确定相关记录）。

锚点不是「检索结果」，是独立于检索器的真值：
- literal：锚点文本确实含该实体（地名/物种/摄影师/日期）
- synonym：锚点文本含**原词**，且**不含**查询词——字面检索必然漏，语义检索才该召回
- intent / free：锚点按画面语义组合筛选（any/all 规则），查询词本身不出现在文本中

规则只用于选锚点，评测本身仍跑 web/src/search.js。
"""

import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_groups():
    groups = {}
    for f in sorted((ROOT / "data").glob("*/*.json")):
        if f.parent.name == "thumbs":
            continue
        for r in json.loads(f.read_text(encoding="utf-8")):
            groups.setdefault(r.get("imageKey") or r["id"], r)
    return list(groups.values())


def blob(r, include_desc=False):
    parts = [r.get("title") or "", " ".join(r.get("location") or []), " ".join(r.get("tags") or []),
             " ".join(r.get("content_tags") or []), r.get("photographer") or ""]
    if include_desc:
        parts.append(r.get("desc") or "")
    return " ".join(parts).lower()


# (类别, 查询, 规则, 备注)
# any: 命中任一；all: 全部命中；none: 均不得命中（同义类用来排除字面命中）；limit: 锚点上限
QUERIES = [
    # ---------- A. 字面/实体 25 ----------
    ("literal", "张家界", {"any": ["张家界"], "limit": 30}, "地名"),
    ("literal", "大熊猫", {"any": ["大熊猫", "熊猫"], "limit": 30}, "物种"),
    ("literal", "极光", {"any": ["极光", "北极光"], "limit": 30}, "现象"),
    ("literal", "富士山", {"any": ["富士山"], "limit": 30}, "地标"),
    ("literal", "长城", {"any": ["长城", "慕田峪", "八达岭"], "limit": 30}, "地标"),
    ("literal", "樱花", {"any": ["樱花"], "limit": 30}, "植物"),
    ("literal", "薰衣草", {"any": ["薰衣草"], "limit": 30}, "植物"),
    ("literal", "灯塔", {"any": ["灯塔"], "limit": 30}, "建筑"),
    ("literal", "冰川", {"any": ["冰川"], "limit": 30}, "地貌"),
    ("literal", "珊瑚礁", {"any": ["珊瑚礁"], "limit": 30}, "生态"),
    ("literal", "热气球", {"any": ["热气球"], "limit": 30}, "物件"),
    ("literal", "企鹅", {"any": ["企鹅"], "limit": 30}, "动物"),
    ("literal", "北极熊", {"any": ["北极熊"], "limit": 30}, "动物"),
    ("literal", "火烈鸟", {"any": ["火烈鸟"], "limit": 30}, "动物"),
    ("literal", "蜂鸟", {"any": ["蜂鸟"], "limit": 30}, "动物"),
    ("literal", "梯田", {"any": ["梯田"], "limit": 30}, "地貌"),
    ("literal", "银河", {"any": ["银河"], "limit": 30}, "天象"),
    ("literal", "瀑布", {"any": ["瀑布"], "limit": 30}, "地貌"),
    ("literal", "城堡", {"any": ["城堡"], "limit": 30}, "建筑"),
    ("literal", "寺庙", {"any": ["寺庙", "寺院"], "limit": 30}, "建筑"),
    ("literal", "火车", {"any": ["火车", "铁路"], "limit": 30}, "交通"),
    ("literal", "泰姬陵", {"any": ["泰姬陵", "taj mahal"], "limit": 30}, "地标"),
    ("literal", "Frans Lanting", {"any": ["frans lanting"], "limit": 30}, "摄影师"),
    ("literal", "NASA", {"any": ["nasa"], "limit": 30}, "摄影师/机构"),
    ("literal", "2024-04-06", {"date": "2024-04-06"}, "日期精确查询"),

    # ---------- B. 同义/变体 25（锚点不含查询词，字面必漏） ----------
    ("synonym", "雪峰", {"any": ["雪山"], "none": ["雪峰"], "limit": 8}, "雪山→雪峰"),
    ("synonym", "古堡", {"any": ["城堡"], "none": ["古堡"], "limit": 8}, "城堡→古堡"),
    ("synonym", "悬瀑", {"any": ["瀑布"], "none": ["悬瀑"], "limit": 8}, "瀑布→悬瀑"),
    ("synonym", "水鸟", {"any": ["天鹅", "鹤", "鹈鹕", "鹭", "鸥"], "none": ["水鸟", "新天鹅堡", "天鹅堡"], "limit": 8}, "物种上义词"),
    ("synonym", "红岩荒漠", {"any": ["荒漠", "恶地", "戈壁"], "none": ["红岩"], "limit": 8}, "地貌同义"),
    ("synonym", "极寒之地", {"any": ["冰川", "冰洞", "海冰"], "none": ["极寒"], "limit": 8}, "意译"),
    ("synonym", "金色的麦田", {"any": ["麦田", "干草捆", "麦"], "none": ["金色"], "limit": 8}, "修饰语差异"),
    ("synonym", "摩天大楼", {"any": ["高楼大厦", "高楼", "天际线", "写字楼"], "none": ["摩天大楼"], "limit": 8}, "近义"),
    ("synonym", "冰封的湖面", {"any": ["冰湖", "结冰", "冰封"], "none": ["冰封"], "limit": 8}, "近义"),
    ("synonym", "丛林", {"any": ["雨林", "热带森林"], "none": ["丛林"], "limit": 8}, "近义"),
    ("synonym", "老式火车", {"any": ["蒸汽机车", "蒸汽火车", "机车库", "火车头"], "none": ["老式"], "limit": 8}, "修饰语差异"),
    ("synonym", "雪山湖泊", {"any": ["高山湖", "冰川湖"], "none": ["雪山湖泊"], "limit": 8}, "复合概念"),
    ("synonym", "野花", {"any": ["野花", "花田", "鲜花"], "none": ["野花"], "limit": 8}, "近义"),
    ("synonym", "巨石", {"any": ["岩柱", "巨石阵", "巨石"], "none": ["巨石"], "limit": 8}, "近义"),
    ("synonym", "海岸岩柱", {"any": ["海蚀柱", "礁石"], "none": ["海岸岩柱"], "limit": 8}, "复合概念"),
    ("synonym", "浮冰", {"any": ["浮冰", "海冰"], "none": ["浮冰"], "limit": 8}, "近义"),
    ("synonym", "露天集市", {"any": ["集市"], "none": ["露天"], "limit": 8}, "修饰语差异"),
    ("synonym", "湿地", {"any": ["湿地", "沼泽"], "none": ["湿地"], "limit": 8}, "近义"),
    ("synonym", "发电风车", {"any": ["风车", "风力"], "none": ["发电"], "limit": 8}, "修饰语差异"),
    ("synonym", "古城废墟", {"any": ["废墟", "遗址", "古迹"], "none": ["废墟"], "limit": 8}, "近义"),
    ("synonym", "森林小径", {"any": ["小路", "步道", "小径"], "none": ["小径"], "limit": 8}, "近义"),
    ("synonym", "雪山之巅", {"any": ["山峰", "山顶", "山峦"], "none": ["雪山之巅"], "limit": 8}, "复合概念"),
    ("synonym", "深林", {"any": ["森林", "树林"], "none": ["深林"], "limit": 8}, "近义"),
    ("synonym", "湍流", {"any": ["溪流", "河流", "急流"], "none": ["湍流"], "limit": 8}, "近义"),
    ("synonym", "高山草甸", {"any": ["草原", "草地", "草甸"], "none": ["高山草甸"], "limit": 8}, "复合概念"),

    # ---------- C. 意图/风格 25 ----------
    ("intent", "极简", {"any": ["极简"], "limit": 10}, "风格（标签几乎为零）"),
    ("intent", "适合当桌面的深色壁纸", {"any": ["夜景", "剪影"], "limit": 8}, "使用场景"),
    ("intent", "城市天际线", {"all": ["城市"], "any": ["天际线", "夜景", "高楼"], "limit": 8}, "意图"),
    ("intent", "温暖的秋色", {"any": ["秋色", "秋天", "秋季"], "limit": 8}, "氛围"),
    ("intent", "寒冷刺骨", {"any": ["雪", "冰"], "limit": 8}, "体感"),
    ("intent", "热带度假", {"any": ["海滩", "棕榈", "热带"], "limit": 8}, "场景"),
    ("intent", "荒无人烟", {"any": ["荒漠", "恶地", "戈壁", "荒原"], "limit": 8}, "氛围"),
    ("intent", "建筑摄影", {"any": ["建筑"], "limit": 8}, "题材"),
    ("intent", "花卉特写", {"all": ["花"], "any": ["微距", "特写"], "limit": 8}, "构图"),
    ("intent", "星空下的风景", {"any": ["银河", "星空"], "limit": 8}, "场景"),
    ("intent", "水面倒影", {"any": ["倒影"], "limit": 8}, "构图"),
    ("intent", "剪影", {"any": ["剪影"], "limit": 8}, "构图"),
    ("intent", "航拍视角", {"any": ["航拍"], "limit": 8}, "构图"),
    ("intent", "晨雾", {"any": ["晨雾"], "limit": 8}, "天气"),
    ("intent", "冬季运动", {"any": ["滑雪"], "limit": 8}, "活动"),
    ("intent", "野生动物", {"any": ["野生动物"], "limit": 8}, "题材"),
    ("intent", "海洋生物", {"any": ["珊瑚", "海洋", "鱼"], "limit": 8}, "题材"),
    ("intent", "几何构图", {"any": ["几何"], "limit": 8}, "构图"),
    ("intent", "古老建筑", {"any": ["古建筑", "历史建筑", "遗迹"], "limit": 8}, "题材"),
    ("intent", "街头人文", {"any": ["人群", "集市", "街道"], "limit": 8}, "题材"),
    ("intent", "山间小径", {"any": ["小路", "步道"], "limit": 8}, "场景"),
    ("intent", "日落剪影", {"all": ["剪影"], "any": ["日落", "晚霞", "黄昏"], "limit": 8}, "构图"),
    ("intent", "冰雪世界", {"any": ["冰雪", "冰雕", "冰洞"], "limit": 8}, "题材"),
    ("intent", "田园生活", {"any": ["农田", "乡村", "牧场", "农庄"], "limit": 8}, "场景"),
    ("intent", "云海", {"any": ["云海"], "limit": 8}, "天气"),

    # ---------- D. 自由语言 25 ----------
    ("free", "一个人都没有的雪原", {"all": ["雪"], "any": ["荒原", "雪原", "平原", "苔原"], "limit": 8}, "自然语言"),
    ("free", "像童话一样的森林", {"any": ["森林"], "limit": 8}, "自然语言"),
    ("free", "发光的海水", {"any": ["荧光"], "limit": 8}, "自然语言"),
    ("free", "从天上看下去的城市", {"all": ["城市"], "any": ["航拍"], "limit": 8}, "自然语言"),
    ("free", "被雪覆盖的树", {"all": ["雪"], "any": ["树"], "limit": 8}, "自然语言"),
    ("free", "山谷里的晨雾", {"all": ["晨雾"], "any": ["山谷", "峡谷", "山"], "limit": 8}, "自然语言"),
    ("free", "悬崖边的小镇", {"any": ["悬崖"], "limit": 8}, "自然语言"),
    ("free", "沙漠里的星空", {"all": ["星空", "银河"], "any": ["沙漠", "荒漠"], "limit": 8}, "自然语言"),
    ("free", "水面上的倒影", {"any": ["倒影"], "limit": 8}, "自然语言"),
    ("free", "一群飞过天空的鸟", {"any": ["鸟群"], "limit": 8}, "自然语言"),
    ("free", "金色的秋天树林", {"all": ["秋色"], "any": ["树", "森林"], "limit": 8}, "自然语言"),
    ("free", "蓝到透明的海水", {"any": ["清澈海水", "蓝绿色海水"], "limit": 8}, "自然语言"),
    ("free", "冰川里的蓝色洞穴", {"any": ["冰洞"], "limit": 8}, "自然语言"),
    ("free", "沙漠中的湖泊", {"all": ["湖"], "any": ["沙漠", "荒漠"], "limit": 8}, "自然语言"),
    ("free", "高山上的花海", {"all": ["花"], "any": ["山", "高山"], "limit": 8}, "自然语言"),
    ("free", "雨后的彩虹", {"any": ["彩虹"], "limit": 8}, "自然语言"),
    ("free", "夜晚的城市灯光", {"any": ["城市灯光", "夜景"], "limit": 8}, "自然语言"),
    ("free", "孤独的灯塔", {"any": ["灯塔"], "limit": 8}, "自然语言"),
    ("free", "森林里的小路", {"all": ["森林", "树"], "any": ["小路", "步道"], "limit": 8}, "自然语言"),
    ("free", "夕阳下的古堡", {"all": ["城堡"], "any": ["日落", "晚霞", "黄昏"], "limit": 8}, "自然语言"),
    ("free", "极地里的一家子", {"all": ["幼"], "any": ["企鹅", "北极熊", "海豹"], "limit": 8}, "自然语言"),
    ("free", "盛开的花田", {"any": ["花田", "花海", "花园"], "limit": 8}, "自然语言"),
    ("free", "一条穿过草原的河", {"all": ["草原"], "any": ["河"], "limit": 8}, "自然语言"),
    ("free", "云海日出", {"all": ["云"], "any": ["日出"], "limit": 8}, "自然语言"),
    ("free", "星轨", {"any": ["星轨"], "limit": 10}, "长期摄影"),
]


def main():
    groups = load_groups()
    out = []
    for cat, q, rule, note in QUERIES:
        if "date" in rule:
            anchors = [r["id"] for r in groups if r["date"] == rule["date"]]
        else:
            cands = []
            for r in groups:
                b = blob(r)
                if not any(w.lower() in b for w in rule.get("any", [])):
                    continue
                if not all(w.lower() in b for w in rule.get("all", [])):
                    continue
                if any(w.lower() in b for w in rule.get("none", [])):
                    continue
                cands.append(r["id"])
            # 随机采样而非取文件序前 N 条：分片按市场字母序加载，取前 N 会让锚点全落在 de-de
            limit = rule.get("limit", 8)
            anchors = cands if len(cands) <= limit else random.Random(q).sample(cands, limit)
        out.append({"query": q, "category": cat, "note": note, "anchors": anchors})

    empty = [o["query"] for o in out if not o["anchors"]]
    (ROOT / "web/eval/queries.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"查询 {len(out)} 条，无锚点 {len(empty)} 条: {empty}")
    for cat in ("literal", "synonym", "intent", "free"):
        rows = [o for o in out if o["category"] == cat]
        n = sum(len(o["anchors"]) for o in rows)
        print(f"  {cat}: {len(rows)} 条 / 锚点 {n}（均 {n / max(len(rows), 1):.1f}）")


if __name__ == "__main__":
    main()
