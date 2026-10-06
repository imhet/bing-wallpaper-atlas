# Bing 壁纸索引站 · 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建一个 Bing 每日壁纸的元数据索引站：Python 抓取结构化元数据到分片 JSON，Vue 3 静态站提供关键词/时间/地区/摄影师/分辨率搜索，GitHub Actions 每日自动更新并部署到 GitHub Pages。

**Architecture:** 三个目录零后端——`crawler/`（Python，只抓元数据不下载图片）、`data/`（按市场×年分片的 JSON，git 提交，即 API）、`web/`（Vue 3 + Vite，浏览器内 MiniSearch 搜索 + JS 过滤）。Actions 每日跑增量抓取，有数据 diff 才 commit 并部署。

**Tech Stack:** Python 3.11+（requests、jsonschema、pytest）；Node 20 + Vue 3.5 + Vite 6 + MiniSearch 7 + vitest；GitHub Actions + Pages。

**Spec:** `docs/superpowers/specs/2026-10-06-bing-wallpaper-index-design.md`（实现时与计划一起阅读，规格以 spec 为准）

## Global Constraints

- Python ≥3.11，Node ≥20。Python 依赖仅 `requests`、`jsonschema`（运行时）+ `pytest`（开发）；不引入其他依赖
- 记录字段名与 spec §6 完全一致：`id, market, date, urlbase, imageKey, title, desc, location, region, photographer, gallery, copyrightlink, quiz, resolutions, tags`，多一字段少一字段都不行（schema `additionalProperties: false`）
- 数据文件内 market 一律小写（`zh-cn`）；调 Bing 接口时转大写（`zh-CN`）
- `data/` 内 JSON 一律 `ensure_ascii=False`、`indent=1`、文件尾换行；聚合文件不得含时间戳字段（保证无变化时零 git diff）
- 对 Bing CDN 的批量请求限速 5 req/s（间隔 0.2s）
- 提交信息用 `feat:`/`test:`/`chore:`/`docs:`/`data:` 前缀，结尾加 `Co-Authored-By: Claude Code <noreply@anthropic.com>`
- **禁止用截图验证**（当前模型不支持图片输入）：前端一律用日志、`curl`、HTML 文本、vitest 输出验证
- 解析类函数遇到异常输入**永不抛异常**：返回空值并保留原始 `desc`
- 所有 Python 命令在仓库根目录、venv 激活状态下运行：`source .venv/bin/activate`

## Review Focus

spec 隐含但单测之外最可能咬人的五类输入（每条已钉进对应任务的测试步骤）：

1. **copyright 字符串变体**（英文句子式、无图库、尾部带日期、完全无括号）→ 解析永不抛异常、`desc` 原文永远保留 — Task 2
2. **接口异常响应**（images 空数组、缺字段、startdate 格式坏）→ 跳过或明确报错，不产出脏数据 — Task 5
3. **重复运行回填/抓取** → 幂等：同 id 记录不重复、内容不变不产生 diff — Task 7、10、11
4. **中文连续关键词**（「中国雪山」无空格）→ 单字切分 AND 命中，AND 无结果回退 OR — Task 13
5. **图片链接 404** → 该分辨率记 false，前端只展示/下载 true 的（thumb 不作为可选档位）— Task 6、15
6. **niumoo `date` 比 Bing `startdate` 系统性 +1 天**（真实数据 8/8 实证）→ 源头归一化减一天 + 回填自检断言「同 (market, imageKey) 零重复、零未来日期」— Task 9、12
7. **本地（中国出口）网络把所有市场的请求路由到 zh-CN feed** → 回填前 `verify_mkt` 预检剔除未通过市场，预检不过禁止无限定回填 — Task 10、12
8. **年切换日的新分片文件是未跟踪状态，`git diff` 看不见** → Actions 先 `git add -A data/` 再 `git diff --cached --quiet` 判断 — Task 16

---

### Task 1: 项目脚手架 + 市场分级配置

**Files:**
- Create: `.gitignore`、`requirements.txt`、`requirements-dev.txt`、`crawler/__init__.py`、`crawler/markets.py`、`tests/__init__.py`、`tests/test_markets.py`

**Interfaces:**
- Produces: `crawler/markets.py` 导出 `CORE_MARKETS: list[str]`、`EXTENDED_MARKETS: list[str]`、`EXTENDED_ENABLED: bool`、`all_markets() -> list[str]`、`to_api_mkt(market: str) -> str`

- [ ] **Step 0: 确认在 git 仓库内**

```bash
git rev-parse --is-inside-work-tree || git init -b main
```
Expected: `true`（若目录从未 git init 则此步完成初始化）

- [ ] **Step 1: 写脚手架文件**

`.gitignore`:
```
.venv/
__pycache__/
*.pyc
.pytest_cache/
node_modules/
web/dist/
```

`requirements.txt`:
```
requests>=2.31
jsonschema>=4.21
```

`requirements-dev.txt`:
```
-r requirements.txt
pytest>=8
```

`crawler/__init__.py` 与 `tests/__init__.py` 均为空文件。

`crawler/markets.py`:
```python
"""市场分级配置：核心市场每日必抓且失败告警，扩展市场可整体启停。"""

CORE_MARKETS = ["zh-cn", "en-us"]
EXTENDED_MARKETS = ["ja-jp", "en-gb", "de-de", "fr-fr", "ko-kr", "zh-tw"]
EXTENDED_ENABLED = True


def all_markets() -> list[str]:
    return CORE_MARKETS + (EXTENDED_MARKETS if EXTENDED_ENABLED else [])


def to_api_mkt(market: str) -> str:
    """'zh-cn' -> 'zh-CN'"""
    lang, region = market.split("-")
    return f"{lang}-{region.upper()}"
```

- [ ] **Step 2: 写失败测试**

`tests/test_markets.py`:
```python
from crawler.markets import CORE_MARKETS, EXTENDED_MARKETS, all_markets, to_api_mkt


def test_core_markets():
    assert CORE_MARKETS == ["zh-cn", "en-us"]


def test_extended_markets():
    assert EXTENDED_MARKETS == ["ja-jp", "en-gb", "de-de", "fr-fr", "ko-kr", "zh-tw"]


def test_all_markets_contains_both_tiers():
    markets = all_markets()
    assert "zh-cn" in markets and "ja-jp" in markets


def test_to_api_mkt():
    assert to_api_mkt("zh-cn") == "zh-CN"
    assert to_api_mkt("en-us") == "en-US"
```

- [ ] **Step 3: 建环境并跑测试确认失败**

```bash
cd /Users/het/work/dev/workspace/ai/bing-wallpaper
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest tests/test_markets.py -v
```
Expected: 4 passed（此时 markets.py 已写好，应直接通过；若任何 import 失败先修复）

- [ ] **Step 4: 确认 pytest 通过**

Run: `python -m pytest tests/ -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add .gitignore requirements.txt requirements-dev.txt crawler/ tests/
git commit -m "chore: 项目脚手架与市场分级配置

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 2: copyright 解析器 + imageKey 提取

**Files:**
- Create: `crawler/copyright_parser.py`、`crawler/image_key.py`
- Test: `tests/test_copyright_parser.py`、`tests/test_image_key.py`

**Interfaces:**
- Produces: `parse_copyright(desc: str) -> dict`，返回 `{"photographer": str|None, "gallery": str|None, "location": list[str]}`；`extract_image_key(urlbase: str) -> str|None`。任何输入不抛异常。

- [ ] **Step 1: 写失败测试**

`tests/test_copyright_parser.py`:
```python
from crawler.copyright_parser import parse_copyright


def test_standard_zh():
    r = parse_copyright("丹霞地貌，张掖国家地质公园，甘肃省，中国 (© Weiquan Lin/Getty Images)")
    assert r["photographer"] == "Weiquan Lin"
    assert r["gallery"] == "Getty Images"
    assert r["location"] == ["丹霞地貌", "张掖国家地质公园", "甘肃省", "中国"]


def test_no_gallery():
    r = parse_copyright("湖畔晨雾 (© 张三)")
    assert r["photographer"] == "张三"
    assert r["gallery"] is None


def test_english_sentence_location_is_single_item():
    r = parse_copyright("View of Edinburgh Castle from a churchyard in Scotland (© Chris Dorney/Alamy)")
    assert r["photographer"] == "Chris Dorney"
    assert r["gallery"] == "Alamy"
    assert r["location"] == ["View of Edinburgh Castle from a churchyard in Scotland"]


def test_trailing_date_stripped():
    r = parse_copyright("阿尔忒弥斯1号月球火箭，39B发射台，肯尼迪航天中心，佛罗里达州，2022年6月15日 (© EVA MARIE UZCATEGUI/Getty Images)")
    assert r["location"] == ["阿尔忒弥斯1号月球火箭", "39B发射台", "肯尼迪航天中心", "佛罗里达州"]
    assert r["photographer"] == "EVA MARIE UZCATEGUI"


def test_no_bracket_keeps_text_as_location():
    r = parse_copyright("神秘湖泊风光")
    assert r["photographer"] is None
    assert r["gallery"] is None
    assert r["location"] == ["神秘湖泊风光"]


def test_empty_and_none_never_raise():
    assert parse_copyright("") == {"photographer": None, "gallery": None, "location": []}
    assert parse_copyright(None) == {"photographer": None, "gallery": None, "location": []}


def test_nested_brackets_in_photographer_field():
    r = parse_copyright("湖上日出 (© 张三(李四)/Getty Images)")
    assert r["photographer"] == "张三"
    assert r["gallery"] == "Getty Images"


def test_pure_date_desc_location_empty():
    r = parse_copyright("2022年6月15日 (© 张三)")
    assert r["photographer"] == "张三"
    assert r["location"] == []
```

`tests/test_image_key.py`:
```python
from crawler.image_key import extract_image_key


def test_extract():
    assert extract_image_key("/th?id=OHR.DanxiaLandform_ZH-CN2386060246") == "DanxiaLandform"


def test_none_when_no_match():
    assert extract_image_key("/th?id=whatever") is None
    assert extract_image_key("") is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_copyright_parser.py tests/test_image_key.py -v`
Expected: FAIL（ModuleNotFoundError: crawler.copyright_parser）

- [ ] **Step 3: 实现**

`crawler/copyright_parser.py`:
```python
"""解析 Bing copyright 字符串：'内容 (© 摄影师/图库)'。

永不抛异常：解析不出就返回空值，调用方保留原始 desc。
"""

import re

_DATE_RE = re.compile(r"^(\d{4}年)?\d{1,2}月\d{1,2}日$")
# inner 用贪婪匹配吃到字符串最外层闭括号，兼容摄影师名内嵌套的括号（Bing desc 至多一个 © 括号块）
_BRACKET_RE = re.compile(r"[（(]\s*©\s*(?P<inner>.*)[)）]")


def _empty_result():
    return {"photographer": None, "gallery": None, "location": []}


def parse_copyright(desc):
    if not desc:
        return _empty_result()
    result = _empty_result()
    text = desc
    m = _BRACKET_RE.search(desc)
    if m:
        inner = m.group("inner").strip()
        inner = re.sub(r"[（(][^)）]*[)）]", "", inner).strip()  # 剥掉摄影师名内嵌套的配对括号
        if "/" in inner:
            photographer, _, gallery = inner.partition("/")
            result["photographer"] = photographer.strip() or None
            result["gallery"] = gallery.strip() or None
        else:
            result["photographer"] = inner or None
        text = (desc[: m.start()] + " " + desc[m.end() :]).strip()
    text = text.strip(" ,，、-–—")
    parts = [p.strip() for p in re.split(r"[,，]", text) if p.strip()]
    if parts and _DATE_RE.match(parts[-1]):
        parts = parts[:-1]
    result["location"] = parts
    return result
```

`crawler/image_key.py`:
```python
"""从 urlbase 提取跨市场的图片标识。"""

import re

_RE = re.compile(r"OHR\.([A-Za-z0-9]+?)_[A-Z]{2}-[A-Z]{2}\d+$")


def extract_image_key(urlbase):
    if not urlbase:
        return None
    m = _RE.search(urlbase)
    return m.group(1) if m else None
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_copyright_parser.py tests/test_image_key.py -v`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add crawler/copyright_parser.py crawler/image_key.py tests/test_copyright_parser.py tests/test_image_key.py
git commit -m "feat: copyright 解析器与 imageKey 提取

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 3: 国家地区词表与提取

**Files:**
- Create: `crawler/regions.py`
- Test: `tests/test_regions.py`

**Interfaces:**
- Consumes: `parse_copyright` 产出的 `location: list[str]`
- Produces: `extract_region(location: list[str], full_text: str) -> str|None`；`COUNTRY_ALIASES: dict[str, str]`（alias 小写 → 规范名）

- [ ] **Step 1: 写失败测试**

`tests/test_regions.py`:
```python
from crawler.regions import extract_region


def test_zh_chain_tail_match():
    assert extract_region(["丹霞地貌", "张掖国家地质公园", "甘肃省", "中国"], "丹霞地貌，张掖国家地质公园，甘肃省，中国") == "中国"


def test_en_tail_match():
    assert extract_region(["Kasilof River", "Alaska", "USA"], "Kasilof River, Alaska, USA") == "美国"


def test_en_fulltext_match():
    assert extract_region(["View of Edinburgh Castle from a churchyard in Scotland"], "View of Edinburgh Castle from a churchyard in Scotland") == "英国"


def test_short_latin_alias_needs_word_boundary():
    # 'us' 不能因子串出现在 'russia' 里而误判
    assert extract_region([], "Kaliningrad, Russia") == "俄罗斯"
    assert extract_region([], "russett landscape") is None


def test_long_latin_alias_needs_word_boundary():
    # 'america' 不能因子串出现在 'American' 里而压过 canada
    assert extract_region(["Canadian Rockies"], "American robin perched in Canada") == "加拿大"


def test_continent_phrases_do_not_become_countries():
    # 南美/北美是地理区域不是国家；'South America' 不应命中 america→美国
    assert extract_region(["Amazon rainforest"], "Amazon rainforest in South America") is None
    assert extract_region([], "Seoul, South Korea") == "韩国"  # 负向短语只挡特定别名


def test_no_match_returns_none():
    assert extract_region(["神秘湖泊风光"], "神秘湖泊风光") is None
    assert extract_region([], "") is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_regions.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现**

`crawler/regions.py`:
```python
"""国家/地区词表与提取。词表是可维护的起点清单，遇到未覆盖地区直接加条目。"""

import re

COUNTRY_ALIASES = {
    "中国": "中国", "中华人民共和国": "中国",
    "美国": "美国", "美利坚合众国": "美国", "united states": "美国", "usa": "美国", "us": "美国", "america": "美国",
    "英国": "英国", "英格兰": "英国", "苏格兰": "英国", "威尔士": "英国", "北爱尔兰": "英国",
    "united kingdom": "英国", "uk": "英国", "england": "英国", "scotland": "英国", "wales": "英国",
    "日本": "日本", "japan": "日本",
    "德国": "德国", "germany": "德国",
    "法国": "法国", "france": "法国",
    "韩国": "韩国", "south korea": "韩国", "korea": "韩国",
    "加拿大": "加拿大", "canada": "加拿大",
    "澳大利亚": "澳大利亚", "australia": "澳大利亚",
    "新西兰": "新西兰", "new zealand": "新西兰",
    "意大利": "意大利", "italy": "意大利",
    "西班牙": "西班牙", "spain": "西班牙",
    "葡萄牙": "葡萄牙", "portugal": "葡萄牙",
    "瑞士": "瑞士", "switzerland": "瑞士",
    "挪威": "挪威", "norway": "挪威",
    "瑞典": "瑞典", "sweden": "瑞典",
    "芬兰": "芬兰", "finland": "芬兰",
    "丹麦": "丹麦", "denmark": "丹麦", "法罗群岛": "丹麦", "faroe islands": "丹麦",
    "荷兰": "荷兰", "netherlands": "荷兰",
    "比利时": "比利时", "belgium": "比利时",
    "奥地利": "奥地利", "austria": "奥地利",
    "爱尔兰": "爱尔兰", "ireland": "爱尔兰",
    "希腊": "希腊", "greece": "希腊",
    "土耳其": "土耳其", "turkey": "土耳其",
    "俄罗斯": "俄罗斯", "russia": "俄罗斯",
    "印度": "印度", "india": "印度",
    "泰国": "泰国", "thailand": "泰国",
    "越南": "越南", "vietnam": "越南",
    "印度尼西亚": "印度尼西亚", "indonesia": "印度尼西亚",
    "马来西亚": "马来西亚", "malaysia": "马来西亚",
    "新加坡": "新加坡", "singapore": "新加坡",
    "菲律宾": "菲律宾", "philippines": "菲律宾",
    "尼泊尔": "尼泊尔", "nepal": "尼泊尔",
    "不丹": "不丹", "bhutan": "不丹",
    "缅甸": "缅甸", "myanmar": "缅甸", "burma": "缅甸",
    "柬埔寨": "柬埔寨", "cambodia": "柬埔寨",
    "老挝": "老挝", "laos": "老挝",
    "斯里兰卡": "斯里兰卡", "sri lanka": "斯里兰卡",
    "巴基斯坦": "巴基斯坦", "pakistan": "巴基斯坦",
    "哈萨克斯坦": "哈萨克斯坦", "kazakhstan": "哈萨克斯坦",
    "蒙古": "蒙古", "mongolia": "蒙古",
    "巴西": "巴西", "brazil": "巴西",
    "墨西哥": "墨西哥", "mexico": "墨西哥",
    "阿根廷": "阿根廷", "argentina": "阿根廷",
    "智利": "智利", "chile": "智利",
    "秘鲁": "秘鲁", "peru": "秘鲁",
    "哥伦比亚": "哥伦比亚", "colombia": "哥伦比亚",
    "厄瓜多尔": "厄瓜多尔", "ecuador": "厄瓜多尔",
    "玻利维亚": "玻利维亚", "bolivia": "玻利维亚",
    "乌拉圭": "乌拉圭", "uruguay": "乌拉圭",
    "委内瑞拉": "委内瑞拉", "venezuela": "委内瑞拉",
    "哥斯达黎加": "哥斯达黎加", "costa rica": "哥斯达黎加",
    "巴拿马": "巴拿马", "panama": "巴拿马",
    "南非": "南非", "south africa": "南非",
    "埃及": "埃及", "egypt": "埃及",
    "摩洛哥": "摩洛哥", "morocco": "摩洛哥",
    "突尼斯": "突尼斯", "tunisia": "突尼斯",
    "肯尼亚": "肯尼亚", "kenya": "肯尼亚",
    "坦桑尼亚": "坦桑尼亚", "tanzania": "坦桑尼亚",
    "纳米比亚": "纳米比亚", "namibia": "纳米比亚",
    "博茨瓦纳": "博茨瓦纳", "botswana": "博茨瓦纳",
    "马达加斯加": "马达加斯加", "madagascar": "马达加斯加",
    "南极洲": "南极洲", "antarctica": "南极洲",
    "阿联酋": "阿联酋", "united arab emirates": "阿联酋",
    "沙特阿拉伯": "沙特阿拉伯", "saudi arabia": "沙特阿拉伯",
    "约旦": "约旦", "jordan": "约旦",
    "以色列": "以色列", "israel": "以色列",
    "克罗地亚": "克罗地亚", "croatia": "克罗地亚",
    "匈牙利": "匈牙利", "hungary": "匈牙利",
    "捷克": "捷克", "czech republic": "捷克", "czechia": "捷克",
    "波兰": "波兰", "poland": "波兰",
    "保加利亚": "保加利亚", "bulgaria": "保加利亚",
    "斯洛文尼亚": "斯洛文尼亚", "slovenia": "斯洛文尼亚",
    "斯洛伐克": "斯洛伐克", "slovakia": "斯洛伐克",
    "罗马尼亚": "罗马尼亚", "romania": "罗马尼亚",
    "冰岛": "冰岛", "iceland": "冰岛",
    "格陵兰": "格陵兰", "greenland": "格陵兰",
}

_LOWERED = {k.lower(): v for k, v in COUNTRY_ALIASES.items()}

# 含这些短语时，对应别名的全文匹配作废（大洲/地区名不是国家）
_NEGATIVE_PHRASES = {
    "america": ["south america", "north america", "latin america"],
    "korea": ["north korea"],
}


def _contains(alias, text):
    # 拉丁别名一律按词边界匹配：'us' 不能命中 'russia'，'america' 不能命中 'American'
    if alias.isascii():
        if not re.search(rf"\b{re.escape(alias)}\b", text):
            return False
        for phrase in _NEGATIVE_PHRASES.get(alias, []):
            if phrase in text:
                return False
        return True
    return alias in text


def extract_region(location, full_text):
    for part in reversed(location or []):
        hit = _LOWERED.get(part.strip().lower())
        if hit:
            return hit
    text = (full_text or "").lower()
    hits = [(len(alias), canonical) for alias, canonical in _LOWERED.items() if _contains(alias, text)]
    if hits:
        return max(hits)[1]
    return None
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_regions.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add crawler/regions.py tests/test_regions.py
git commit -m "feat: 国家地区词表与 region 提取

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 4: 记录 schema 校验

**Files:**
- Create: `crawler/schema.py`
- Test: `tests/test_schema.py`

**Interfaces:**
- Produces: `validate_record(rec: dict) -> None`（不合格抛 `jsonschema.ValidationError`）；`SCHEMA: dict`

- [ ] **Step 1: 写失败测试**

`tests/test_schema.py`:
```python
import copy

import pytest

from crawler.schema import validate_record


def make_record(**over):
    rec = {
        "id": "zh-cn-2023-10-05",
        "market": "zh-cn",
        "date": "2023-10-05",
        "urlbase": "/th?id=OHR.ZhangjiajieMist_ZH-CN1234567890",
        "imageKey": "ZhangjiajieMist",
        "title": "云海仙境",
        "desc": "张家界云海 (© Li Hua/Getty Images)",
        "location": ["张家界云海"],
        "region": "中国",
        "photographer": "Li Hua",
        "gallery": "Getty Images",
        "copyrightlink": None,
        "quiz": None,
        "resolutions": {"uhd": True, "fhd": True, "hd": True, "thumb": True},
        "tags": [],
    }
    rec.update(over)
    return rec


def test_valid_record_passes():
    validate_record(make_record())


def test_missing_field_fails():
    rec = make_record()
    del rec["urlbase"]
    with pytest.raises(Exception):
        validate_record(rec)


def test_extra_field_fails():
    with pytest.raises(Exception):
        validate_record(make_record(surprise="x"))


def test_bad_date_format_fails():
    with pytest.raises(Exception):
        validate_record(make_record(date="2023/10/05"))


def test_nullables_accepted():
    rec = make_record(title=None, imageKey=None, region=None, photographer=None, gallery=None)
    validate_record(rec)


def test_resolutions_must_be_bool():
    with pytest.raises(Exception):
        validate_record(make_record(resolutions={"uhd": "yes"}))
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_schema.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现**

`crawler/schema.py`:
```python
"""壁纸记录 JSON Schema。字段与 spec §6 一一对应，additionalProperties 关闭。"""

import jsonschema

SCHEMA = {
    "type": "object",
    "required": [
        "id", "market", "date", "urlbase", "imageKey", "title", "desc",
        "location", "region", "photographer", "gallery",
        "copyrightlink", "quiz", "resolutions", "tags",
    ],
    "additionalProperties": False,
    "properties": {
        "id": {"type": "string", "pattern": "^[a-z]{2}-[a-z]{2}-\\d{4}-\\d{2}-\\d{2}$"},
        "market": {"type": "string", "pattern": "^[a-z]{2}-[a-z]{2}$"},
        "date": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}$"},
        "urlbase": {"type": "string", "pattern": "^/th"},
        "imageKey": {"type": ["string", "null"]},
        "title": {"type": ["string", "null"]},
        "desc": {"type": "string"},
        "location": {"type": "array", "items": {"type": "string"}},
        "region": {"type": ["string", "null"]},
        "photographer": {"type": ["string", "null"]},
        "gallery": {"type": ["string", "null"]},
        "copyrightlink": {"type": ["string", "null"]},
        "quiz": {"type": ["string", "null"]},
        "resolutions": {"type": "object", "additionalProperties": {"type": "boolean"}},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
}


def validate_record(rec):
    jsonschema.validate(rec, SCHEMA)
```

（注：`make_record` 在 Task 10/11 的测试里也要用，把 Step 1 的 `make_record` 挪到 `tests/conftest.py` 并用 `@pytest.fixture` 暴露——本任务实现时即创建 `tests/conftest.py`：

```python
import pytest


@pytest.fixture
def make_record():
    def _make(**over):
        rec = {
            "id": "zh-cn-2023-10-05",
            "market": "zh-cn",
            "date": "2023-10-05",
            "urlbase": "/th?id=OHR.ZhangjiajieMist_ZH-CN1234567890",
            "imageKey": "ZhangjiajieMist",
            "title": "云海仙境",
            "desc": "张家界云海 (© Li Hua/Getty Images)",
            "location": ["张家界云海"],
            "region": "中国",
            "photographer": "Li Hua",
            "gallery": "Getty Images",
            "copyrightlink": None,
            "quiz": None,
            "resolutions": {"uhd": True, "fhd": True, "hd": True, "thumb": True},
            "tags": [],
        }
        rec.update(over)
        return rec
    return _make
```

`tests/test_schema.py` 里删除本地 `make_record`，改为 `def test_valid_record_passes(make_record):` 等以 fixture 注入。）

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_schema.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add crawler/schema.py tests/conftest.py tests/test_schema.py
git commit -m "feat: 壁纸记录 JSON schema 校验

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 5: Bing 接口客户端

**Files:**
- Create: `crawler/bing_api.py`、`tests/fixtures/hp_archive_zh_cn.json`
- Test: `tests/test_bing_api.py`

**Interfaces:**
- Consumes: `to_api_mkt`（Task 1）
- Produces: `fetch_market(market: str, idx: int = 0, n: int = 8, timeout: int = 15, max_retries: int = 3, session=None) -> list[dict]`；每条 raw 记录 `{"market", "date", "urlbase", "title", "desc", "copyrightlink", "quiz"}`；异常类 `BingApiError(RuntimeError)`

- [ ] **Step 1: 录制 fixture**

创建 `tests/fixtures/hp_archive_zh_cn.json`（真实接口响应，已抓取）:
```json
{"images":[{"startdate":"20261005","fullstartdate":"202610051600","enddate":"20261006","url":"/th?id=OHR.DanxiaLandform_ZH-CN2386060246_1920x1080.jpg&rf=LaDigue_1920x1080.jpg&pid=hp","urlbase":"/th?id=OHR.DanxiaLandform_ZH-CN2386060246","copyright":"丹霞地貌，张掖国家地质公园，甘肃省，中国 (© Weiquan Lin/Getty Images)","copyrightlink":"https://www.bing.com/search?q=%E5%9B%BD%E9%99%85%E5%9C%B0%E8%B4%A8%E5%A4%9A%E6%A0%B7%E6%80%A7%E6%97%A5&form=hpcapt&mkt=zh-cn","title":"条纹中的地球故事","quiz":"/search?q=Bing+homepage+quiz&filters=WQOskey:%22HPQuiz_20261005_DanxiaLandform%22&FORM=HPQUIZ","wp":true,"hsh":"e9709af86328b2bb435f7f583234829d","drk":1,"top":1,"bot":1,"hs":[]},{"startdate":"20261004","fullstartdate":"202610041600","enddate":"20261005","url":"/th?id=OHR.AdelieTeacher_ZH-CN2201820679_1920x1080.jpg&rf=LaDigue_1920x1080.jpg&pid=hp","urlbase":"/th?id=OHR.AdelieTeacher_ZH-CN2201820679","copyright":"南极洲的阿德利企鹅 (© Otto Plantema/Minden Pictures)","copyrightlink":"https://www.bing.com/search?q=%E4%B8%96%E7%95%8C%E6%95%99%E5%B8%88%E6%97%A5&form=hpcapt&mkt=zh-cn","title":"纵身一跃，一次一课","quiz":"/search?q=Bing+homepage+quiz&filters=WQOskey:%22HPQuiz_20261004_AdelieTeacher%22&FORM=HPQUIZ","wp":true,"hsh":"70a754d46405850799ade2d1da5d4856","drk":1,"top":1,"bot":1,"hs":[]},{"startdate":"20261003","fullstartdate":"202610031600","enddate":"20261004","url":"/th?id=OHR.ArtemisRocket_ZH-CN1768541365_1920x1080.jpg&rf=LaDigue_1920x1080.jpg&pid=hp","urlbase":"/th?id=OHR.ArtemisRocket_ZH-CN1768541365","copyright":"阿尔忒弥斯1号月球火箭，39B发射台，肯尼迪航天中心，佛罗里达州，2022年6月15日 (© EVA MARIE UZCATEGUI/Getty Images)","copyrightlink":"https://www.bing.com/search?q=%E4%B8%96%E7%95%8C%E7%A9%BA%E9%97%B4%E5%91%A8%E6%97%A5&form=hpcapt&mkt=zh-cn","title":"宇宙在召唤","quiz":"/search?q=Bing+homepage+quiz&filters=WQOskey:%22HPQuiz_20261003_ArtemisRocket%22&FORM=HPQUIZ","wp":false,"hsh":"29bcf53aa5de2328f7af4f284b108f24","drk":1,"top":1,"bot":1,"hs":[]}],"tooltips":{"loading":"正在加载...","previous":"上一个图像","next":"下一个图像","walle":"此图片不能下载用作壁纸。","walls":"下载今日美图。仅限用作桌面壁纸。"}}
```

- [ ] **Step 2: 写失败测试**

`tests/test_bing_api.py`:
```python
import json
from pathlib import Path

import pytest

from crawler.bing_api import BingApiError, fetch_market

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "hp_archive_zh_cn.json").read_text("utf-8"))


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status = status

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": params})
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def test_normalize_fields(monkeypatch):
    monkeypatch.setattr("crawler.bing_api.time.sleep", lambda s: None)
    session = FakeSession([FakeResponse(FIXTURE)])
    records = fetch_market("zh-cn", session=session)
    assert len(records) == 3
    first = records[0]
    assert first == {
        "market": "zh-cn",
        "date": "2026-10-05",
        "urlbase": "/th?id=OHR.DanxiaLandform_ZH-CN2386060246",
        "title": "条纹中的地球故事",
        "desc": "丹霞地貌，张掖国家地质公园，甘肃省，中国 (© Weiquan Lin/Getty Images)",
        "copyrightlink": FIXTURE["images"][0]["copyrightlink"],
        "quiz": FIXTURE["images"][0]["quiz"],
    }


def test_market_param_sent(monkeypatch):
    monkeypatch.setattr("crawler.bing_api.time.sleep", lambda s: None)
    session = FakeSession([FakeResponse({"images": []})])
    fetch_market("ja-jp", session=session)
    assert session.calls[0]["params"]["mkt"] == "ja-JP"


def test_empty_images_ok(monkeypatch):
    monkeypatch.setattr("crawler.bing_api.time.sleep", lambda s: None)
    session = FakeSession([FakeResponse({"images": []})])
    assert fetch_market("zh-cn", session=session) == []


def test_retries_then_raises(monkeypatch):
    monkeypatch.setattr("crawler.bing_api.time.sleep", lambda s: None)
    session = FakeSession([RuntimeError("boom")] * 3)
    with pytest.raises(BingApiError):
        fetch_market("zh-cn", session=session, max_retries=3)


def test_bad_record_skipped_not_fatal(monkeypatch):
    monkeypatch.setattr("crawler.bing_api.time.sleep", lambda s: None)
    bad = dict(FIXTURE["images"][0])
    bad["startdate"] = "202610"  # 坏日期
    payload = {"images": [bad, FIXTURE["images"][1]]}
    session = FakeSession([FakeResponse(payload)])
    records = fetch_market("zh-cn", session=session)
    assert [r["date"] for r in records] == ["2026-10-04"]  # 坏记录跳过，好记录保留
```

- [ ] **Step 3: 跑测试确认失败**

Run: `python -m pytest tests/test_bing_api.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 4: 实现**

`crawler/bing_api.py`:
```python
"""Bing HPImageArchive 接口客户端（免密钥，仅最近约 15 天）。"""

import time

import requests

from .markets import to_api_mkt

API_URL = "https://www.bing.com/HPImageArchive.aspx"


class BingApiError(RuntimeError):
    pass


def _normalize(img, market):
    """返回 raw 记录；单条坏数据（如 startdate 缺失）返回 None，由调用方跳过。"""
    sd = str(img.get("startdate", ""))
    if len(sd) != 8 or not sd.isdigit():
        return None
    return {
        "market": market,
        "date": f"{sd[0:4]}-{sd[4:6]}-{sd[6:8]}",
        "urlbase": img.get("urlbase"),
        "title": img.get("title") or None,
        "desc": img.get("copyright", ""),
        "copyrightlink": img.get("copyrightlink") or None,
        "quiz": img.get("quiz") or None,
    }


def fetch_market(market, idx=0, n=8, timeout=15, max_retries=3, session=None):
    session = session or requests
    params = {"format": "js", "idx": idx, "n": n, "mkt": to_api_mkt(market)}
    last_err = None
    for attempt in range(max_retries):
        try:
            resp = session.get(API_URL, params=params, timeout=timeout)
            resp.raise_for_status()
            records = (_normalize(img, market) for img in resp.json().get("images", []))
            return [r for r in records if r]  # 坏记录跳过，重试只留给网络类错误
        except (requests.RequestException, ValueError, RuntimeError) as e:
            last_err = e
            time.sleep(2 ** attempt)
    raise BingApiError(f"{market} idx={idx} failed after {max_retries} attempts: {last_err}") from last_err
```

- [ ] **Step 5: 跑测试确认通过**

Run: `python -m pytest tests/test_bing_api.py -v`
Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
git add crawler/bing_api.py tests/fixtures/ tests/test_bing_api.py
git commit -m "feat: Bing 接口客户端（重试与响应规范化）

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 6: 分辨率 HEAD 验证

**Files:**
- Create: `crawler/resolutions.py`
- Test: `tests/test_resolutions.py`

**Interfaces:**
- Produces: `RESOLUTION_SUFFIXES: list[tuple[str, str]]`（key→后缀）、`check_resolutions(urlbase: str, session=None, interval: float = 0.2) -> dict[str, bool]`（单档 404 记 false；**全部请求网络级失败时返回 `{}`**，表示系统性故障、留待重试）

- [ ] **Step 1: 写失败测试**

`tests/test_resolutions.py`:
```python
from crawler.resolutions import RESOLUTION_SUFFIXES, check_resolutions


class FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code


class FakeSession:
    def __init__(self, status_map):
        self.status_map = status_map
        self.urls = []

    def head(self, url, timeout=None, allow_redirects=True):
        self.urls.append(url)
        for suffix, status in self.status_map.items():
            if url.endswith(suffix):
                return FakeResponse(status)
        return FakeResponse(404)


def test_suffix_list():
    keys = [k for k, _ in RESOLUTION_SUFFIXES]
    assert keys == ["uhd", "fhd", "hd", "thumb"]
    assert dict(RESOLUTION_SUFFIXES)["uhd"] == "_UHD.jpg"


def test_check(monkeypatch):
    monkeypatch.setattr("crawler.resolutions.time.sleep", lambda s: None)
    session = FakeSession({"_UHD.jpg": 200, "_1920x1080.jpg": 200, "_1366x768.jpg": 404, "_400x240.jpg": 200})
    result = check_resolutions("/th?id=OHR.Test_ZH-CN1234567890", session=session)
    assert result == {"uhd": True, "fhd": True, "hd": False, "thumb": True}
    assert len(session.urls) == 4
    assert session.urls[0] == "https://www.bing.com/th?id=OHR.Test_ZH-CN1234567890_UHD.jpg"


def test_single_network_error_means_false(monkeypatch):
    monkeypatch.setattr("crawler.resolutions.time.sleep", lambda s: None)

    class Flaky:
        def __init__(self):
            self.n = 0

        def head(self, url, timeout=None, allow_redirects=True):
            self.n += 1
            if self.n == 1:
                raise ConnectionError("down")  # 单次网络错误
            return FakeResponse(200)

    result = check_resolutions("/th?id=OHR.X_ZH-CN1", session=Flaky())
    assert result["uhd"] is False  # 单档失败记 false
    assert result["fhd"] is True


def test_all_network_errors_return_empty(monkeypatch):
    # 系统性网络故障返回 {}：与"图链 404 是真实状态"区分，让回填下轮重试
    monkeypatch.setattr("crawler.resolutions.time.sleep", lambda s: None)

    class Dead:
        def head(self, url, timeout=None, allow_redirects=True):
            raise ConnectionError("down")

    assert check_resolutions("/th?id=OHR.X_ZH-CN1", session=Dead()) == {}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_resolutions.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现**

`crawler/resolutions.py`:
```python
"""对 Bing CDN 候选分辨率后缀做 HEAD 验证。限速 5 req/s。"""

import time

import requests

BASE = "https://www.bing.com"
RESOLUTION_SUFFIXES = [
    ("uhd", "_UHD.jpg"),
    ("fhd", "_1920x1080.jpg"),
    ("hd", "_1366x768.jpg"),
    ("thumb", "_400x240.jpg"),
]
REQUEST_INTERVAL = 0.2


def check_resolutions(urlbase, session=None, interval=REQUEST_INTERVAL):
    session = session or requests
    out = {}
    errors = 0
    for key, suffix in RESOLUTION_SUFFIXES:
        url = f"{BASE}{urlbase}{suffix}"
        try:
            resp = session.head(url, timeout=10, allow_redirects=True)
            out[key] = resp.status_code == 200
        except (requests.RequestException, OSError):
            # OSError 兜底裸 ConnectionError（内置异常与 requests 异常是兄弟类）
            out[key] = False
            errors += 1
        time.sleep(interval)
    if errors == len(RESOLUTION_SUFFIXES):
        return {}  # 全部网络级失败视为系统性故障：返回空让下轮回填重试，不固化 false
    return out
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_resolutions.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add crawler/resolutions.py tests/test_resolutions.py
git commit -m "feat: 分辨率可用性 HEAD 验证

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 7: data 分片存储 + 聚合生成

**Files:**
- Create: `crawler/storage.py`
- Test: `tests/test_storage.py`

**Interfaces:**
- Consumes: 合法记录 dict（Task 4 schema）
- Produces: `load_year(data_dir, market, year) -> list[dict]`；`save_year(data_dir, market, year, records) -> None`（按 date 升序落盘）；`upsert_record(data_dir, rec) -> bool`（新增/更新 True，内容不变 False）；`load_all(data_dir) -> dict[str, list[dict]]`；`write_aggregations(data_dir) -> None`

- [ ] **Step 1: 写失败测试**

`tests/test_storage.py`:
```python
import json

from crawler.storage import load_all, load_year, save_year, upsert_record, write_aggregations


def test_save_and_load_roundtrip(tmp_path, make_record):
    save_year(tmp_path, "zh-cn", 2023, [make_record(date="2023-10-05", id="zh-cn-2023-10-05"),
                                        make_record(date="2023-10-04", id="zh-cn-2023-10-04")])
    assert load_year(tmp_path, "zh-cn", 2023)[0]["date"] == "2023-10-04"  # 已按 date 升序
    assert load_year(tmp_path, "zh-cn", 2099) == []


def test_upsert_insert_and_idempotent(tmp_path, make_record):
    rec = make_record()
    assert upsert_record(tmp_path, rec) is True
    assert upsert_record(tmp_path, rec) is False  # 内容不变
    changed = make_record(title="新标题")
    assert upsert_record(tmp_path, changed) is True
    assert len(load_year(tmp_path, "zh-cn", 2023)) == 1


def test_load_all_scans_markets(tmp_path, make_record):
    upsert_record(tmp_path, make_record())
    upsert_record(tmp_path, make_record(market="en-us", id="en-us-2023-10-05"))
    all_data = load_all(tmp_path)
    assert set(all_data) == {"zh-cn", "en-us"}


def test_write_aggregations(tmp_path, make_record):
    upsert_record(tmp_path, make_record())
    upsert_record(tmp_path, make_record(market="en-us", id="en-us-2023-10-05", photographer="Li Hua"))
    upsert_record(tmp_path, make_record(market="en-us", id="en-us-2023-10-06", date="2023-10-06", photographer="Bob"))
    write_aggregations(tmp_path)
    agg = json.loads((tmp_path / "aggregations.json").read_text("utf-8"))
    assert agg["markets"] == ["en-us", "zh-cn"]
    assert agg["years"] == [2023]
    assert agg["years_by_market"] == {"en-us": [2023], "zh-cn": [2023]}
    assert agg["total"] == 3
    names = [p["name"] for p in agg["photographers"]]
    assert set(names) == {"Li Hua", "Bob"}
    assert "updated_at" not in agg  # 零 diff 约束：禁止时间戳字段


def test_load_all_ignores_aggregations_file(tmp_path, make_record):
    upsert_record(tmp_path, make_record())
    write_aggregations(tmp_path)
    assert set(load_all(tmp_path)) == {"zh-cn"}  # aggregations.json 不是市场目录
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_storage.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现**

`crawler/storage.py`:
```python
"""data/ 目录的分片读写与聚合文件生成。

布局：data/{market}/{year}.json 为按 date 升序的记录数组；
data/aggregations.json 为聚合文件。无时间戳字段保证零 diff。
"""

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


def year_shard_path(data_dir, market, year):
    return Path(data_dir) / market / f"{year}.json"


def load_year(data_dir, market, year):
    p = year_shard_path(data_dir, market, year)
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


def save_year(data_dir, market, year, records):
    p = year_shard_path(data_dir, market, year)
    p.parent.mkdir(parents=True, exist_ok=True)
    records = sorted(records, key=lambda r: r["date"])
    p.write_text(json.dumps(records, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def upsert_record(data_dir, rec):
    year = int(rec["date"][:4])
    records = load_year(data_dir, rec["market"], year)
    for i, existing in enumerate(records):
        if existing["id"] == rec["id"]:
            if existing == rec:
                return False
            records[i] = rec
            save_year(data_dir, rec["market"], year, records)
            return True
    records.append(rec)
    save_year(data_dir, rec["market"], year, records)
    return True


def load_all(data_dir):
    out = defaultdict(list)
    root = Path(data_dir)
    if not root.exists():
        return {}
    for market_dir in sorted(root.iterdir()):
        if not market_dir.is_dir():
            continue
        for f in sorted(market_dir.glob("*.json")):
            out[market_dir.name].extend(json.loads(f.read_text(encoding="utf-8")))
    return dict(out)


def write_aggregations(data_dir):
    all_recs = [r for recs in load_all(data_dir).values() for r in recs]

    def counted(field):
        c = Counter(r[field] for r in all_recs if r.get(field))
        return [{"name": k, "count": v} for k, v in c.most_common()]

    years_by_market = defaultdict(set)
    for r in all_recs:
        years_by_market[r["market"]].add(int(r["date"][:4]))
    agg = {
        "photographers": counted("photographer"),
        "regions": counted("region"),
        "markets": sorted({r["market"] for r in all_recs}),
        "years": sorted({int(r["date"][:4]) for r in all_recs}),
        "years_by_market": {m: sorted(ys) for m, ys in sorted(years_by_market.items())},
        "total": len(all_recs),
    }
    p = Path(data_dir) / "aggregations.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(agg, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
```

（实现里未使用的 `datetime` 导入不要写——上面 import 行只保留 `json`、`Counter/defaultdict`、`Path`。）

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_storage.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add crawler/storage.py tests/test_storage.py
git commit -m "feat: data 分片存储与聚合生成

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 8: 字段级互补合并

**Files:**
- Create: `crawler/merge.py`
- Test: `tests/test_merge.py`

**Interfaces:**
- Produces: `merge_records(*records: dict) -> dict`——后面的源优先（非空字段覆盖前面的）；`market`/`date` 不一致抛 `ValueError`

- [ ] **Step 1: 写失败测试**

`tests/test_merge.py`:
```python
import pytest

from crawler.merge import merge_records


def test_later_source_wins_on_conflict():
    a = {"market": "zh-cn", "date": "2023-10-05", "desc": "旧描述", "title": None}
    b = {"market": "zh-cn", "date": "2023-10-05", "desc": "新描述", "title": "标题"}
    merged = merge_records(a, b)
    assert merged["desc"] == "新描述"
    assert merged["title"] == "标题"


def test_later_source_fills_gaps_without_losing_data():
    a = {"market": "zh-cn", "date": "2023-10-05", "desc": "描述", "quiz": "q"}
    b = {"market": "zh-cn", "date": "2023-10-05", "desc": "描述", "title": "标题", "quiz": None}
    merged = merge_records(a, b)
    assert merged["title"] == "标题"
    assert merged["quiz"] == "q"


def test_key_conflict_raises():
    with pytest.raises(ValueError):
        merge_records({"market": "zh-cn", "date": "2023-10-05"}, {"market": "en-us", "date": "2023-10-05"})


def test_single_record_passthrough():
    r = {"market": "zh-cn", "date": "2023-10-05", "desc": "x"}
    assert merge_records(r) == r
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_merge.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现**

`crawler/merge.py`:
```python
"""多来源记录的字段级互补合并。

规则：后面的源优先——非空字段覆盖前面的；空值不覆盖已有非空值。
"""


def _empty(v):
    return v is None or v == "" or v == []


def merge_records(*records):
    if not records:
        raise ValueError("no records to merge")
    merged = {}
    for rec in records:
        for key in ("market", "date"):
            if key in merged and rec.get(key) != merged[key]:
                raise ValueError(f"{key} conflict: {merged[key]!r} vs {rec.get(key)!r}")
        for k, v in rec.items():
            if not _empty(v):
                merged[k] = v
    return merged
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_merge.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add crawler/merge.py tests/test_merge.py
git commit -m "feat: 多来源记录字段级互补合并

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 9: 回填源适配器（niumoo + Bing API）

**Files:**
- Create: `crawler/sources/__init__.py`（空）、`crawler/sources/niumoo_source.py`、`crawler/sources/bing_api_source.py`、`tests/fixtures/niumoo_images.json`
- Test: `tests/test_sources.py`

**Interfaces:**
- Consumes: `fetch_market`（Task 5）、`CORE_MARKETS/EXTENDED_MARKETS/EXTENDED_ENABLED`（Task 1）
- Produces: `NiumooSource().fetch(session=None) -> list[dict]`、`BingApiSource().fetch() -> list[dict]`；两者产出与 Task 5 raw 记录同构的 dict（`market, date, urlbase, title, desc, copyrightlink, quiz`），niumoo 的 `url` 剥离分辨率后缀成 `/th?id=OHR.xxx_XX-XX123` 形式，且 niumoo 的 `date` 统一减一天对齐 Bing startdate 语义、按 (market, date) 去重、丢弃未来日期

- [ ] **Step 1: 录制 fixture**

`tests/fixtures/niumoo_images.json`（真实数据节选；注意 niumoo 的 date 比 Bing startdate 系统性 +1 天，见实现里的归一化）:
```json
[
  {"date": "2026-10-06", "region": "zh-cn", "url": "https://cn.bing.com/th?id=OHR.DanxiaLandform_ZH-CN2386060246_UHD.jpg&rf=LaDigue_UHD.jpg&pid=hp&w=3840&h=2160&rs=1&c=4", "desc": "丹霞地貌，张掖国家地质公园，甘肃省，中国 (© Weiquan Lin/Getty Images)"},
  {"date": "2026-10-05", "region": "zh-cn", "url": "https://cn.bing.com/th?id=OHR.AdelieTeacher_ZH-CN2201820679_UHD.jpg&rf=LaDigue_UHD.jpg&pid=hp&w=3840&h=2160&rs=1&c=4", "desc": "南极洲的阿德利企鹅 (© Otto Plantema/Minden Pictures)"},
  {"date": "2024-10-31", "region": "en-us", "url": "https://cn.bing.com/th?id=OHR.HauntedEdinburgh_EN-US3906244993_UHD.jpg", "desc": "View of Edinburgh Castle from a churchyard in Scotland (© Chris Dorney/Alamy)"},
  {"date": "2026-10-06", "region": "zh-cn", "url": "https://cn.bing.com/th?id=OHR.GrizzlySwim_ZH-CN1005455737_UHD.jpg", "desc": "美国阿拉斯加州棕熊 (© Danny Green/Nature Picture Library)"},
  {"date": "2099-01-01", "region": "zh-cn", "url": "https://cn.bing.com/th?id=OHR.FuturePic_ZH-CN9999999999_UHD.jpg", "desc": "未来日期条目应被丢弃"}
]
```

- [ ] **Step 2: 写失败测试**

`tests/test_sources.py`:
```python
import base64
import json
from pathlib import Path

from crawler.sources.bing_api_source import BingApiSource
from crawler.sources.niumoo_source import NiumooSource

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "niumoo_images.json").read_text("utf-8"))


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, payload):
        self.payload = payload

    def get(self, url, timeout=None):
        return FakeResponse(self.payload)


def test_niumoo_fetch_normalizes():
    session = FakeSession(FIXTURE)
    records = NiumooSource().fetch(session=session)
    # 5 条原始数据：Danxia/Adelie/Edinburgh 保留，GrizzlySwim 归一化后与 Danxia 同日去重，2099 未来条目丢弃
    assert len(records) == 3
    first = records[0]
    assert first["market"] == "zh-cn"
    assert first["date"] == "2026-10-05"  # 2026-10-06 - 1 天，对齐 Bing startdate（真实配对实证）
    assert first["urlbase"] == "/th?id=OHR.DanxiaLandform_ZH-CN2386060246"
    assert first["title"] is None and first["copyrightlink"] is None
    assert "丹霞地貌" in first["desc"]
    assert [r["date"] for r in records] == ["2026-10-05", "2026-10-04", "2024-10-30"]


def test_niumoo_accepts_github_api_base64(monkeypatch):
    wrapped = {"content": base64.b64encode(json.dumps(FIXTURE).encode()).decode()}
    session = FakeSession(wrapped)
    records = NiumooSource().fetch(session=session)
    assert len(records) == 3


def test_niumoo_skips_bad_urls():
    bad = [{"date": "2024-01-01", "region": "zh-cn", "url": "https://example.com/nope.jpg", "desc": "x"}]
    records = NiumooSource().fetch(session=FakeSession(bad))
    assert records == []


def test_bing_api_source_covers_all_markets(monkeypatch):
    seen = []
    monkeypatch.setattr("crawler.sources.bing_api_source.fetch_market",
                        lambda market, idx=0, n=8: (seen.append(market), [{"market": market, "date": "2026-10-06", "urlbase": "/th?id=OHR.X_XX-XX1", "title": None, "desc": "", "copyrightlink": None, "quiz": None}])[1])
    records = BingApiSource().fetch()
    assert set(seen) == {"zh-cn", "en-us", "ja-jp", "en-gb", "de-de", "fr-fr", "ko-kr", "zh-tw"}
    assert len(records) == 8
```

- [ ] **Step 3: 跑测试确认失败**

Run: `python -m pytest tests/test_sources.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 4: 实现**

`crawler/sources/niumoo_source.py`:
```python
"""niumoo/bing-wallpaper 仓库 images.json 回填源。

本地网络拉不到 raw.githubusercontent 时，可设环境变量
NIUMOO_JSON_URL=https://api.github.com/repos/niumoo/bing-wallpaper/contents/docs/images.json
（自动识别 GitHub contents API 的 base64 包装并解码）。
"""

import base64
import json
import os
import re
from datetime import datetime, timedelta

import requests

NIUMOO_URL = os.environ.get(
    "NIUMOO_JSON_URL",
    "https://raw.githubusercontent.com/niumoo/bing-wallpaper/main/docs/images.json",
)
_OHR_RE = re.compile(r"OHR\.[A-Za-z0-9]+?_[A-Z]{2}-[A-Z]{2}\d+")


def _shift_date(date_str):
    """niumoo 的 date 比 Bing startdate 系统性 +1 天（真实数据 8/8 实证），统一减一天对齐。坏值返回 None。"""
    try:
        return (datetime.strptime(date_str, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return None


class NiumooSource:
    name = "niumoo"

    def fetch(self, session=None):
        session = session or requests
        resp = session.get(NIUMOO_URL, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and "content" in data:  # GitHub contents API 包装
            data = json.loads(base64.b64decode(data["content"]))
        if not isinstance(data, list):
            raise ValueError(f"unexpected niumoo payload type: {type(data)}")
        today = datetime.now().strftime("%Y-%m-%d")
        out = []
        seen = set()  # (market, date) 去重：源数据有 51 组同日重复条目
        for item in data:
            m = _OHR_RE.search(item.get("url", "") or "")
            if not m:
                continue
            date = _shift_date(item.get("date"))
            if not date or date > today:  # 坏日期 / 未来日期丢弃
                continue
            key = (item["region"].lower(), date)
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "market": item["region"].lower(),
                "date": date,
                "urlbase": f"/th?id={m.group(0)}",
                "title": None,
                "desc": item.get("desc", "") or "",
                "copyrightlink": None,
                "quiz": None,
            })
        return out
```

`crawler/sources/bing_api_source.py`:
```python
"""Bing 官方接口回填源（补充 title/copyrightlink 等富字段，仅最近约 15 天）。"""

from ..bing_api import fetch_market
from ..markets import EXTENDED_ENABLED, EXTENDED_MARKETS, CORE_MARKETS


class BingApiSource:
    name = "bing-api"

    def fetch(self):
        markets = list(CORE_MARKETS) + (EXTENDED_MARKETS if EXTENDED_ENABLED else [])
        out = []
        for market in markets:
            out.extend(fetch_market(market, idx=0, n=8))
        return out
```

- [ ] **Step 5: 跑测试确认通过**

Run: `python -m pytest tests/test_sources.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add crawler/sources/ tests/fixtures/niumoo_images.json tests/test_sources.py
git commit -m "feat: niumoo 与 Bing API 回填源适配器

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 10: 回填入口

**Files:**
- Create: `crawler/backfill.py`
- Test: `tests/test_backfill.py`

**Interfaces:**
- Consumes: Task 2/3/4/6/7/8/9 全部
- Produces: `build_record(merged: dict) -> dict`（raw 合并记录 → 含 id/location/region/photographer/gallery/imageKey/tags 的最终记录，resolutions 为空 dict）；`verify_mkt(markets: list[str], session=None) -> list[str]`（逐市场预检 mkt 生效性，返回通过列表）；`run_backfill(data_dir="data", check_res=True, markets=None) -> None`（单条记录失败只记日志不中断）；CLI `python -m crawler.backfill [--data-dir DIR] [--skip-resolution-check] [--markets zh-cn,en-us]`

- [ ] **Step 1: 写失败测试**

`tests/test_backfill.py`:
```python
import json

from crawler.backfill import build_record, run_backfill, verify_mkt
from crawler.storage import load_year


def test_build_record_parses_everything():
    merged = {
        "market": "zh-cn", "date": "2026-10-05",
        "urlbase": "/th?id=OHR.AdelieTeacher_ZH-CN2201820679",
        "title": "纵身一跃，一次一课",
        "desc": "南极洲的阿德利企鹅 (© Otto Plantema/Minden Pictures)",
        "copyrightlink": "https://www.bing.com/search?q=x", "quiz": None,
    }
    rec = build_record(merged)
    assert rec["id"] == "zh-cn-2026-10-05"
    assert rec["imageKey"] == "AdelieTeacher"
    assert rec["region"] == "南极洲" or rec["region"] is None  # 词表未覆盖时允许 None
    assert rec["photographer"] == "Otto Plantema"
    assert rec["gallery"] == "Minden Pictures"
    assert rec["tags"] == []


def test_build_record_bad_url_never_crashes():
    rec = build_record({"market": "zh-cn", "date": "2026-10-05", "urlbase": "", "title": None, "desc": "", "copyrightlink": None, "quiz": None})
    assert rec["imageKey"] is None


def test_run_backfill_end_to_end(tmp_path, monkeypatch):
    niumoo_payload = [
        {"date": "2026-10-05", "region": "zh-cn", "url": "https://cn.bing.com/th?id=OHR.AdelieTeacher_ZH-CN2201820679_UHD.jpg", "desc": "南极洲的阿德利企鹅 (© Otto Plantema/Minden Pictures)"},
        {"date": "2026-10-04", "region": "en-us", "url": "https://cn.bing.com/th?id=OHR.HauntedEdinburgh_EN-US3906244993_UHD.jpg", "desc": "View of Edinburgh Castle from a churchyard in Scotland (© Chris Dorney/Alamy)"},
    ]
    bing_payload = [{
        "market": "zh-cn", "date": "2026-10-05",
        "urlbase": "/th?id=OHR.AdelieTeacher_ZH-CN2201820679",
        "title": "纵身一跃，一次一课",
        "desc": "南极洲的阿德利企鹅 (© Otto Plantema/Minden Pictures)",
        "copyrightlink": "https://www.bing.com/search?q=x", "quiz": None,
    }]

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            pass

        def json(self):
            return self._payload

    class FakeSession:
        def get(self, url, timeout=None):
            return FakeResponse(niumoo_payload)

    monkeypatch.setattr("crawler.sources.niumoo_source.requests", FakeSession())
    monkeypatch.setattr("crawler.backfill.check_resolutions",
                        lambda urlbase, **kw: {"uhd": True, "fhd": True, "hd": True, "thumb": True})
    monkeypatch.setattr("crawler.backfill.NiumooSource", lambda: _StubNiumoo(niumoo_payload))
    monkeypatch.setattr("crawler.backfill.BingApiSource", lambda: _StubBing(bing_payload))
    monkeypatch.setattr("crawler.backfill.verify_mkt", lambda markets, session=None: list(markets))

    run_backfill(data_dir=tmp_path, check_res=False)

    zh = load_year(tmp_path, "zh-cn", 2026)
    assert len(zh) == 1
    rec = zh[0]
    assert rec["title"] == "纵身一跃，一次一课"  # Bing API 源覆盖了 niumoo 的 None
    assert rec["resolutions"] == {}
    us = load_year(tmp_path, "en-us", 2026)
    assert us[0]["photographer"] == "Chris Dorney"
    assert json.loads((tmp_path / "aggregations.json").read_text("utf-8"))["total"] == 2


def test_verify_mkt_excludes_polluted_market(monkeypatch):
    # 本地（中国出口）网络下 ja-jp 请求实际拿到 zh-CN feed，必须被预检剔除
    def fake_fetch(market, idx=0, n=1, session=None):
        return [{"market": market, "date": "2026-10-06",
                 "urlbase": "/th?id=OHR.KasilofRiver_ZH-CN2394091052",
                 "title": None, "desc": "", "copyrightlink": None, "quiz": None}]

    monkeypatch.setattr("crawler.backfill.fetch_market", fake_fetch)
    assert verify_mkt(["zh-cn", "ja-jp"]) == ["zh-cn"]


def test_run_backfill_one_bad_record_does_not_abort(tmp_path, monkeypatch):
    class _RawStub:
        def fetch(self, session=None):
            return [
                {"market": "zh-cn", "date": "2026-10-05", "urlbase": "/th?id=OHR.Good1_ZH-CN1111111111",
                 "title": None, "desc": "ok", "copyrightlink": None, "quiz": None},
                # urlbase 不满足 schema 的 ^/th → validate_record 在落盘循环里抛错，必须只跳过不中断
                {"market": "zh-cn", "date": "2026-10-06", "urlbase": "BAD",
                 "title": None, "desc": "bad urlbase", "copyrightlink": None, "quiz": None},
            ]

    monkeypatch.setattr("crawler.backfill.NiumooSource", lambda: _RawStub())
    monkeypatch.setattr("crawler.backfill.BingApiSource", lambda: _StubBing([]))
    monkeypatch.setattr("crawler.backfill.verify_mkt", lambda markets, session=None: list(markets))

    run_backfill(data_dir=tmp_path, check_res=False)  # 不抛异常即通过
    assert len(load_year(tmp_path, "zh-cn", 2026)) == 1


class _StubNiumoo:
    def __init__(self, payload):
        self.payload = payload

    def fetch(self, session=None):
        from crawler.sources.niumoo_source import _OHR_RE

        return [{
            "market": i["region"].lower(), "date": i["date"],
            "urlbase": f"/th?id={_OHR_RE.search(i['url']).group(0)}",
            "title": None, "desc": i["desc"], "copyrightlink": None, "quiz": None,
        } for i in self.payload]


class _StubBing:
    def __init__(self, payload):
        self.payload = payload

    def fetch(self):
        return self.payload
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_backfill.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现**

`crawler/backfill.py`:
```python
"""历史回填入口：跑全部源 → 按(市场,日期)合并 → 解析/校验/落盘 → 聚合。

幂等：已存在且带 resolutions 的记录跳过，可反复重跑。
"""

import argparse
import logging
import re

from .bing_api import fetch_market
from .copyright_parser import parse_copyright
from .image_key import extract_image_key
from .merge import merge_records
from .regions import extract_region
from .resolutions import check_resolutions
from .schema import validate_record
from .sources.bing_api_source import BingApiSource
from .sources.niumoo_source import NiumooSource
from .storage import load_year, upsert_record, write_aggregations

log = logging.getLogger(__name__)


def verify_mkt(markets, session=None):
    """逐市场预检 mkt 参数是否生效（防止本地网络把所有市场路由到 zh-CN feed）。返回通过的市场。"""
    ok = []
    for market in markets:
        try:
            recs = fetch_market(market, idx=0, n=1, session=session)
        except Exception as e:
            log.warning("mkt preflight failed (api error): %s: %s", market, e)
            continue
        expected = market.upper()  # zh-cn -> ZH-CN
        if recs and re.search(rf"_{expected}\d+", recs[0]["urlbase"] or ""):
            ok.append(market)
        else:
            log.warning("mkt preflight failed: %s 未返回本市场数据（疑似被网络位置覆盖），已剔除", market)
    return ok


def build_record(merged):
    loc = parse_copyright(merged.get("desc", ""))
    desc = merged.get("desc", "") or ""
    return {
        "id": f'{merged["market"]}-{merged["date"]}',
        "market": merged["market"],
        "date": merged["date"],
        "urlbase": merged.get("urlbase") or "",
        "imageKey": extract_image_key(merged.get("urlbase") or ""),
        "title": merged.get("title"),
        "desc": desc,
        "location": loc["location"],
        "region": extract_region(loc["location"], desc),
        "photographer": loc["photographer"],
        "gallery": loc["gallery"],
        "copyrightlink": merged.get("copyrightlink"),
        "quiz": merged.get("quiz"),
        "resolutions": {},
        "tags": [],
    }


def run_backfill(data_dir="data", check_res=True, markets=None):
    sources = [NiumooSource(), BingApiSource()]
    by_key = {}
    for src in sources:
        try:
            items = src.fetch()
        except Exception as e:  # 单个源失败不拖垮整个回填
            log.warning("source %s failed: %s", src.name, e)
            continue
        for r in items:
            if markets and r["market"] not in markets:
                continue
            by_key.setdefault((r["market"], r["date"]), []).append(r)

    valid_markets = set(verify_mkt(sorted({m for m, _ in by_key})))
    added = skipped = failed = 0
    for (market, date), recs in sorted(by_key.items()):
        if market not in valid_markets:
            continue
        try:
            merged = merge_records(*recs)
            rec = build_record(merged)
            year = int(date[:4])
            existing = [r for r in load_year(data_dir, market, year) if r["id"] == rec["id"]]
            if existing and existing[0].get("resolutions"):
                skipped += 1
                continue
            if check_res:
                rec["resolutions"] = check_resolutions(rec["urlbase"])
            validate_record(rec)
        except Exception as e:  # 单条坏记录只跳过，不中断整个回填
            failed += 1
            log.warning("record %s-%s failed: %s", market, date, e)
            continue
        if upsert_record(data_dir, rec):
            added += 1
    write_aggregations(data_dir)
    log.info("backfill done: added=%d skipped=%d failed=%d", added, skipped, failed)


def main():
    parser = argparse.ArgumentParser(description="Bing 壁纸历史回填")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--skip-resolution-check", action="store_true")
    parser.add_argument("--markets", default="", help="逗号分隔，仅回填这些市场（空=全部）")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    markets = [m.strip() for m in args.markets.split(",") if m.strip()] or None
    run_backfill(data_dir=args.data_dir, check_res=not args.skip_resolution_check, markets=markets)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_backfill.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add crawler/backfill.py tests/test_backfill.py
git commit -m "feat: 历史回填入口（幂等可重跑）

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 11: 每日增量入口

**Files:**
- Create: `crawler/fetch_daily.py`
- Test: `tests/test_fetch_daily.py`

**Interfaces:**
- Consumes: `fetch_market`、`build_record`（Task 10）、`check_resolutions`、`upsert_record`/`write_aggregations`、`CORE_MARKETS`/`EXTENDED_MARKETS`/`EXTENDED_ENABLED`
- Produces: `run_daily(data_dir="data") -> tuple[bool, bool]`（`(changed, core_failed)`）；CLI `python -m crawler.fetch_daily [--data-dir DIR]`，核心市场失败时退出码 1

- [ ] **Step 1: 写失败测试**

`tests/test_fetch_daily.py`:
```python
import crawler.fetch_daily as fd
from crawler.storage import load_year


def raw(market, date, key):
    return {"market": market, "date": date, "urlbase": f"/th?id=OHR.{key}_XX-XX1",
            "title": None, "desc": "somewhere, China (© A/B)", "copyrightlink": None, "quiz": None}


def test_daily_inserts_new_and_reports_changed(tmp_path, monkeypatch):
    monkeypatch.setattr(fd, "fetch_market",
                        lambda market, idx=0, n=8: [raw(market, "2026-10-06", "NewOne")] if market == "zh-cn" else [])
    monkeypatch.setattr(fd, "check_resolutions", lambda urlbase, **kw: {"uhd": True, "fhd": True, "hd": True, "thumb": True})
    changed, core_failed = fd.run_daily(data_dir=tmp_path)
    assert changed is True and core_failed is False
    assert load_year(tmp_path, "zh-cn", 2026)[0]["id"] == "zh-cn-2026-10-06"


def test_daily_idempotent_no_change(tmp_path, monkeypatch):
    monkeypatch.setattr(fd, "fetch_market", lambda market, idx=0, n=8: [raw(market, "2026-10-06", "NewOne")])
    monkeypatch.setattr(fd, "check_resolutions", lambda urlbase, **kw: {"uhd": True, "fhd": True, "hd": True, "thumb": True})
    fd.run_daily(data_dir=tmp_path)
    changed, core_failed = fd.run_daily(data_dir=tmp_path)
    assert changed is False and core_failed is False


def test_core_failure_sets_flag_and_skips_extended(tmp_path, monkeypatch):
    calls = []

    def boom(market, idx=0, n=8):
        calls.append(market)
        if market == "zh-cn":
            raise fd.BingApiError("down")
        return []

    monkeypatch.setattr(fd, "fetch_market", boom)
    changed, core_failed = fd.run_daily(data_dir=tmp_path)
    assert core_failed is True
    assert "ja-jp" not in calls  # 核心失败后扩展市场确实未被请求


def test_bad_record_in_daily_does_not_poison_market(tmp_path, monkeypatch):
    def fetch(market, idx=0, n=8):
        if market != "zh-cn":
            return []
        return [
            {"market": "zh-cn", "date": "2026-10-06", "urlbase": "/th?id=OHR.Good_ZH-CN1111111111",
             "title": None, "desc": "ok", "copyrightlink": None, "quiz": None},
            {"market": "zh-cn", "date": "2026-10-07", "urlbase": "BAD",  # schema 校验会失败
             "title": None, "desc": "x", "copyrightlink": None, "quiz": None},
        ]

    monkeypatch.setattr(fd, "fetch_market", fetch)
    monkeypatch.setattr(fd, "check_resolutions", lambda urlbase, **kw: {"uhd": True, "fhd": True, "hd": True, "thumb": True})
    changed, core_failed = fd.run_daily(data_dir=tmp_path)
    assert core_failed is False
    assert len(load_year(tmp_path, "zh-cn", 2026)) == 1  # 坏记录跳过，好记录入库


def test_extended_failure_is_not_fatal(tmp_path, monkeypatch):
    def flaky(market, idx=0, n=8):
        if market == "ja-jp":
            raise fd.BingApiError("down")
        return [raw(market, "2026-10-06", "K")] if market == "zh-cn" else []

    monkeypatch.setattr(fd, "fetch_market", flaky)
    monkeypatch.setattr(fd, "check_resolutions", lambda urlbase, **kw: {"uhd": True})
    changed, core_failed = fd.run_daily(data_dir=tmp_path)
    assert core_failed is False and changed is True


def test_main_exits_1_on_core_failure(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(fd, "run_daily", lambda data_dir="data": (False, True))
    monkeypatch.setattr("sys.argv", ["fetch_daily.py", "--data-dir", str(tmp_path)])
    try:
        fd.main()
        code = 0
    except SystemExit as e:
        code = e.code
    assert code == 1
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_fetch_daily.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现**

`crawler/fetch_daily.py`:
```python
"""每日增量入口：核心市场必抓（失败告警退出码 1），扩展市场尽力抓。

n=8 窗口容忍漏抓；无新数据时不产生 git diff（Actions 据此跳过部署）。
"""

import argparse
import logging
import sys

from .backfill import build_record
from .bing_api import BingApiError, fetch_market
from .markets import CORE_MARKETS, EXTENDED_ENABLED, EXTENDED_MARKETS
from .resolutions import check_resolutions
from .schema import validate_record
from .storage import upsert_record, write_aggregations

log = logging.getLogger(__name__)


def ingest_market(market, data_dir):
    added = 0
    for rawrec in fetch_market(market, idx=0, n=8):
        try:
            rec = build_record(rawrec)
            rec["resolutions"] = check_resolutions(rec["urlbase"])
            validate_record(rec)
        except Exception as e:  # 单条坏记录跳过，不毒化整个市场
            log.warning("skip bad record %s/%s: %s", market, rawrec.get("date"), e)
            continue
        if upsert_record(data_dir, rec):
            added += 1
    return added


def run_daily(data_dir="data"):
    changed = False
    core_failed = False
    for market in CORE_MARKETS:
        try:
            n = ingest_market(market, data_dir)
            changed = changed or n > 0
            log.info("core %s: +%d", market, n)
        except Exception as e:
            core_failed = True
            log.error("core market %s failed: %s", market, e)
    if core_failed:
        log.error("skipping extended markets because a core market failed")
        return changed, core_failed
    if EXTENDED_ENABLED:
        for market in EXTENDED_MARKETS:
            try:
                n = ingest_market(market, data_dir)
                changed = changed or n > 0
            except Exception as e:
                log.warning("extended market %s failed (non-fatal): %s", market, e)
    write_aggregations(data_dir)
    return changed, core_failed


def main():
    parser = argparse.ArgumentParser(description="Bing 壁纸每日增量抓取")
    parser.add_argument("--data-dir", default="data")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    changed, core_failed = run_daily(data_dir=args.data_dir)
    log.info("changed=%s core_failed=%s", changed, core_failed)
    if core_failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_fetch_daily.py -v`
Expected: 6 passed

- [ ] **Step 5: 全量测试回归**

Run: `python -m pytest tests/ -v`
Expected: 全部通过（累计约 60 个用例）

- [ ] **Step 6: Commit**

```bash
git add crawler/fetch_daily.py tests/test_fetch_daily.py
git commit -m "feat: 每日增量抓取入口（核心/扩展市场分级容错）

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 12: 执行真实历史回填（真实数据落盘）

**Files:**
- Create: `data/`（脚本产物，git 提交）

**Interfaces:**
- Consumes: `python -m crawler.backfill`、`crawler.backfill.verify_mkt`
- Produces: `data/zh-cn/2023..2026.json`、`data/en-us/2021..2026.json`、`data/aggregations.json`（真实历史数据，约 3400 条；扩展市场数据从 Task 17 首次 Actions run 开始积累，本地不回填）

- [ ] **Step 0: mkt 生效性预检（必须最先做，防止污染数据入库）**

```bash
source .venv/bin/activate
python - <<'EOF'
import logging
logging.basicConfig(level=logging.INFO)
from crawler.backfill import verify_mkt
ok = verify_mkt(["zh-cn", "en-us", "ja-jp"])
print("preflight ok:", ok)
EOF
```
Expected: 至少 `zh-cn` 通过。判断规则：`ja-jp` 也在通过列表 → 本网络 mkt 生效，后续步骤可全量回填（去掉 `--markets` 参数）；`ja-jp` 未通过（本地网络被路由到 zh-CN feed，中国出口常见）→ 后续所有回填命令必须带 `--markets zh-cn,en-us`，扩展市场数据等 Task 17 首次 Actions run（美国出口）自然积累。**预检不过就不允许无限定回填。**

- [ ] **Step 1: 先跑小样本验证（跳过分辨率验证，秒级）**

```bash
python -m crawler.backfill --data-dir /tmp/bw-smoke --skip-resolution-check --markets zh-cn,en-us
python - <<'EOF'
import json
from collections import defaultdict
from datetime import date
from pathlib import Path
agg = json.loads(Path("/tmp/bw-smoke/aggregations.json").read_text())
print("markets:", agg["markets"], "total:", agg["total"])
print("years_by_market:", agg["years_by_market"])
today = date.today().isoformat()
by_key = defaultdict(set)
future = 0
n = 0
for f in Path("/tmp/bw-smoke").glob("*/*.json"):
    for r in json.loads(f.read_text()):
        n += 1
        if r["imageKey"]:
            by_key[(r["market"], r["imageKey"])].add(r["date"])
        if r["date"] > today:
            future += 1
dupes = {k: sorted(v) for k, v in by_key.items() if len(v) > 1}
print("同(market,imageKey)多日期记录组:", len(dupes), list(dupes.items())[:5])
print("未来日期记录数:", future)
filled_ph = sum(1 for f in Path("/tmp/bw-smoke").glob("*/*.json") for r in json.loads(f.read_text()) if r["photographer"])
print(f"photographer 填充率: {filled_ph}/{n}")
assert not dupes, f"日期体系未对齐，同图出现多日期重复: {list(dupes.items())[:3]}"
assert future == 0, "存在未来日期记录"
print("SMOKE OK")
EOF
```
Expected: `SMOKE OK`；total ≈ 3400+；zh-cn 覆盖 2023-2026、en-us 覆盖 2021-2026；photographer 填充率 > 95%。**若重复断言失败，说明 niumoo 日期偏移假设有问题——停下来向需求方报告，不得带病继续。**
⚠️ 若本地网络拉不到 raw.githubusercontent（返回空），改用：
`NIUMOO_JSON_URL=https://api.github.com/repos/niumoo/bing-wallpaper/contents/docs/images.json python -m crawler.backfill --data-dir /tmp/bw-smoke --skip-resolution-check --markets zh-cn,en-us`

- [ ] **Step 2: 正式回填到 data/（含分辨率验证，约 45 分钟，后台运行）**

```bash
nohup python -m crawler.backfill --data-dir data --markets zh-cn,en-us > backfill.log 2>&1 &
echo "backfill started, monitor: tail -f backfill.log"
```
（Step 0 预检全通过时可去掉 `--markets` 全量回填。）中途可用 `wc -l data/*/*.json` 观察进度。脚本幂等，中断后重跑即可续传。

- [ ] **Step 3: 验证产物（含对抗式审查要求的全部自检）**

```bash
python - <<'EOF'
import json
from collections import defaultdict
from datetime import date
from pathlib import Path
agg = json.loads(Path("data/aggregations.json").read_text())
print("total:", agg["total"])
print("regions top5:", agg["regions"][:5])
print("photographers top3:", agg["photographers"][:3])
today = date.today().isoformat()
by_key = defaultdict(set)
no_res = future = n = 0
for f in Path("data").glob("*/*.json"):
    for r in json.loads(f.read_text()):
        n += 1
        if r["imageKey"]:
            by_key[(r["market"], r["imageKey"])].add(r["date"])
        if not r["resolutions"]:
            no_res += 1
        if r["date"] > today:
            future += 1
dupes = {k: sorted(v) for k, v in by_key.items() if len(v) > 1}
print("重复组:", len(dupes), "| 未来日期:", future, "| resolutions 为空:", no_res, "| 总数:", n)
assert not dupes and future == 0 and no_res == 0
print("DATA OK")
EOF
```
Expected: `DATA OK`；regions 有真实国家名

- [ ] **Step 4: 抽查一条真实记录**

```bash
python - <<'EOF'
import json
from pathlib import Path
recs = json.loads(Path("data/zh-cn/2023.json").read_text())
print(json.dumps(recs[0], ensure_ascii=False, indent=1))
EOF
```
Expected: 完整记录——date/id/urlbase/imageKey/location 链/photographer/gallery/resolutions 均合理

- [ ] **Step 5: Commit**

```bash
git add data/
git commit -m "data: zh-cn/en-us 历史回填（niumoo + Bing API 合并源）

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 13: web 脚手架 + 搜索模块（vitest）

**Files:**
- Create: `web/package.json`、`web/vite.config.js`、`web/index.html`、`web/src/main.js`、`web/src/api.js`、`web/src/search.js`、`web/src/search.test.js`、`web/src/styles.css`（先占位空文件）

**Interfaces:**
- Produces: `api.js` 导出 `fetchJSON(url)`、`loadAggregations()`、`loadShard(market, year)`、`loadAllRecords(aggregations)`、`BING_BASE`、`imageUrl(urlbase, suffix)`、`RES_SUFFIX`、`thumbUrl(record)`；`search.js` 导出 `tokenize(text) -> string[]`、`buildIndex(records) -> MiniSearch`、`searchRecords(index, records, query, filters) -> array`

- [ ] **Step 1: 写脚手架与失败测试**

`web/package.json`:
```json
{
  "name": "bing-wallpaper-web",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview",
    "test": "vitest run"
  },
  "dependencies": {
    "minisearch": "^7.1.0",
    "vue": "^3.5.13"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^5.2.1",
    "vite": "^6.0.7",
    "vitest": "^2.1.8"
  }
}
```

`web/vite.config.js`:
```js
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

export default defineConfig({ base: './', plugins: [vue()] })
```

`web/index.html`:
```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Bing 壁纸索引</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.js"></script>
  </body>
</html>
```

`web/src/main.js`（Task 14 会替换为完整 App；先保证构建通过）:
```js
import { createApp } from 'vue'
import App from './App.vue'
import './styles.css'

createApp(App).mount('#app')
```
（同时创建占位 `web/src/App.vue`：`<template><p>loading…</p></template>`，Task 14 覆盖。）

`web/src/api.js`:
```js
export const BING_BASE = 'https://www.bing.com'
export const RES_SUFFIX = { uhd: '_UHD.jpg', fhd: '_1920x1080.jpg', hd: '_1366x768.jpg' }

export const imageUrl = (urlbase, suffix) => `${BING_BASE}${urlbase}${suffix}`

export const thumbUrl = (r) =>
  r.resolutions?.thumb ? imageUrl(r.urlbase, '_400x240.jpg') : imageUrl(r.urlbase, '_1920x1080.jpg')

export async function fetchJSON(url) {
  const resp = await fetch(url)
  if (!resp.ok) throw new Error(`${url}: HTTP ${resp.status}`)
  return resp.json()
}

export const loadAggregations = () => fetchJSON('./data/aggregations.json')
export const loadShard = (market, year) => fetchJSON(`./data/${market}/${year}.json`)

export async function loadYearShards(aggregations, year) {
  const jobs = []
  for (const [market, years] of Object.entries(aggregations.years_by_market || {}))
    if (years.includes(Number(year))) jobs.push(loadShard(market, Number(year)))
  const shards = await Promise.all(jobs)
  return shards.flat()
}

export async function loadAllRecords(aggregations) {
  const jobs = []
  for (const [market, years] of Object.entries(aggregations.years_by_market || {}))
    for (const year of years) jobs.push(loadShard(market, year))
  const shards = await Promise.all(jobs)
  return shards.flat()
}
```

`web/src/search.js`:
```js
import MiniSearch from 'minisearch'

// 中文单字切分 + 拉丁词整体，'中国雪山' → ['中','国','雪','山']
export function tokenize(text) {
  return (String(text).toLowerCase().match(/[a-z0-9]+|[一-鿿]/g) || [])
}

const FIELDS = ['title', 'desc', 'location', 'region', 'photographer', 'gallery', 'tags']

export function buildIndex(records) {
  const docs = records.map((r) => ({ ...r, location: (r.location || []).join(' ') }))
  const index = new MiniSearch({ fields: FIELDS, storeFields: ['id'], tokenize })
  index.addAll(docs)
  return index
}

export function searchRecords(index, records, query, filters) {
  let result = records
  const q = (query || '').trim()
  if (q) {
    const andIds = new Set(index.search(q, { combineWith: 'AND' }).map((h) => h.id))
    if (andIds.size > 0) {
      result = result.filter((r) => andIds.has(r.id))
    } else {
      // AND 无命中才回退 OR——注意必须从原始 records 过滤，不能在空结果上继续过滤
      const orIds = new Set(index.search(q, { combineWith: 'OR' }).map((h) => h.id))
      result = result.filter((r) => orIds.has(r.id))
    }
  }
  return result.filter(
    (r) =>
      (!filters.market || r.market === filters.market) &&
      (!filters.year || r.date.slice(0, 4) === String(filters.year)) &&
      (!filters.month || r.date.slice(5, 7) === String(filters.month).padStart(2, '0')) &&
      (!filters.region || r.region === filters.region) &&
      (!filters.photographer || r.photographer === filters.photographer) &&
      (!filters.resolution || r.resolutions?.[filters.resolution] === true),
  )
}
```

`web/src/search.test.js`:
```js
import { describe, expect, it } from 'vitest'
import { buildIndex, searchRecords, tokenize } from './search'

const records = [
  { id: 'zh-cn-2023-10-05', market: 'zh-cn', date: '2023-10-05', title: '云海仙境',
    desc: '张家界雪山云海 (© Li Hua/Getty Images)', location: ['张家界国家森林公园'], region: '中国',
    photographer: 'Li Hua', gallery: 'Getty Images', tags: [], resolutions: { uhd: true, thumb: true } },
  { id: 'en-us-2024-01-01', market: 'en-us', date: '2024-01-01', title: 'Winter Alps',
    desc: 'Snowy Alps (© John Doe)', location: ['Snowy Alps'], region: '瑞士',
    photographer: 'John Doe', gallery: null, tags: [], resolutions: { uhd: false, thumb: true } },
]

const index = buildIndex(records)

describe('tokenize', () => {
  it('splits CJK into single chars', () => {
    expect(tokenize('中国雪山')).toEqual(['中', '国', '雪', '山'])
  })
  it('keeps latin words whole and lowercases', () => {
    expect(tokenize('Alaska 2024')).toEqual(['alaska', '2024'])
  })
})

describe('searchRecords', () => {
  it('AND-matches Chinese compound query', () => {
    const hits = searchRecords(index, records, '中国雪山', {})
    expect(hits.map((r) => r.id)).toEqual(['zh-cn-2023-10-05'])
  })

  it('searches by photographer', () => {
    const hits = searchRecords(index, records, 'Li Hua', {})
    expect(hits.map((r) => r.id)).toEqual(['zh-cn-2023-10-05'])
  })

  it('falls back to OR when AND finds nothing', () => {
    // '瑞士张家界'：没有任何记录同时含这两组词 → AND 空 → OR 回退应命中两条
    const hits = searchRecords(index, records, '瑞士张家界', {})
    expect(hits.map((r) => r.id).sort()).toEqual(['en-us-2024-01-01', 'zh-cn-2023-10-05'])
  })

  it('filters by market/year/resolution', () => {
    expect(searchRecords(index, records, '', { market: 'en-us' })).toHaveLength(1)
    expect(searchRecords(index, records, '', { year: 2023 })).toHaveLength(1)
    expect(searchRecords(index, records, '', { resolution: 'uhd' }).map((r) => r.id))
      .toEqual(['zh-cn-2023-10-05'])
    expect(searchRecords(index, records, '', { month: 1 })).toHaveLength(1)
  })
})
```

- [ ] **Step 2: 安装依赖并跑测试**

```bash
cd web && npm install && npm test
```
Expected: 6 个用例全过。若有 MiniSearch API 版本差异导致失败，以 node_modules 里 MiniSearch 实际行为为准修正 `search.js`（保持导出签名不变）

- [ ] **Step 3: 确认构建通过**

Run: `cd web && npm run build`
Expected: `vite build` 成功产出 `web/dist/`（App.vue 还是占位，但可构建）

- [ ] **Step 4: Commit**

```bash
git add web/
git commit -m "feat: web 脚手架与 MiniSearch 中文搜索模块

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 14: 主界面——筛选栏 + 瀑布流 + 页脚

**Files:**
- Create: `web/src/components/FilterBar.vue`、`web/src/components/WallpaperGrid.vue`
- Modify: `web/src/App.vue`（替换占位）、`web/src/styles.css`

**Interfaces:**
- Consumes: `api.js` 全部导出、`search.js` 全部导出（Task 13）
- Produces: `App.vue` 组合根；`FilterBar` props `{aggregations, filters}` emits `update:filters`（filters 形状 `{query, market, year, month, region, photographer, resolution}`）；`WallpaperGrid` props `{records}` emits `select(record)`

- [ ] **Step 1: 写组件**

`web/src/components/FilterBar.vue`:
```vue
<script setup>
const props = defineProps({ aggregations: Object, filters: Object })
const emit = defineEmits(['update:filters'])

function set(key, value) {
  emit('update:filters', { ...props.filters, [key]: value })
}
</script>

<template>
  <div class="filter-bar">
    <input
      class="query"
      :value="filters.query"
      placeholder="搜索标题、地点、摄影师…（如：张家界 雪山）"
      @input="set('query', $event.target.value)"
    />
    <select :value="filters.market" @change="set('market', $event.target.value)">
      <option value="">全部市场</option>
      <option v-for="m in aggregations?.markets || []" :key="m" :value="m">{{ m }}</option>
    </select>
    <select :value="filters.year" @change="set('year', $event.target.value)">
      <option value="">全部年份</option>
      <option v-for="y in aggregations?.years || []" :key="y" :value="y">{{ y }}</option>
    </select>
    <select :value="filters.month" @change="set('month', $event.target.value)">
      <option value="">全部月份</option>
      <option v-for="m in 12" :key="m" :value="m">{{ m }} 月</option>
    </select>
    <select :value="filters.region" @change="set('region', $event.target.value)">
      <option value="">全部国家/地区</option>
      <option v-for="r in aggregations?.regions || []" :key="r.name" :value="r.name">
        {{ r.name }} ({{ r.count }})
      </option>
    </select>
    <select :value="filters.photographer" @change="set('photographer', $event.target.value)">
      <option value="">全部摄影师</option>
      <option v-for="p in aggregations?.photographers || []" :key="p.name" :value="p.name">
        {{ p.name }} ({{ p.count }})
      </option>
    </select>
    <select :value="filters.resolution" @change="set('resolution', $event.target.value)">
      <option value="">全部分辨率</option>
      <option value="uhd">4K UHD</option>
      <option value="fhd">1920×1080</option>
      <option value="hd">1366×768</option>
    </select>
  </div>
</template>
```

`web/src/components/WallpaperGrid.vue`:
```vue
<script setup>
import { thumbUrl } from '../api'

defineProps({ records: Array })
const emit = defineEmits(['select'])
</script>

<template>
  <div class="grid">
    <button v-for="r in records" :key="r.id" class="card" @click="emit('select', r)">
      <img :src="thumbUrl(r)" :alt="r.title || r.desc" loading="lazy" />
      <div class="meta">
        <span class="date">{{ r.date }}</span>
        <span class="title">{{ r.title || r.desc }}</span>
      </div>
    </button>
  </div>
  <p v-if="!records.length" class="empty">没有匹配的壁纸，试试放宽筛选条件。</p>
</template>
```

`web/src/App.vue`:
```vue
<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { loadAggregations, loadAllRecords, loadYearShards } from './api'
import { buildIndex, searchRecords } from './search'
import FilterBar from './components/FilterBar.vue'
import WallpaperGrid from './components/WallpaperGrid.vue'
import WallpaperDetail from './components/WallpaperDetail.vue'

const aggregations = ref(null)
const records = ref([])
const error = ref('')
const loading = ref(true)
const loadingMore = ref(false)
const loadedYears = new Set()
const filters = ref({ query: '', market: '', year: '', month: '', region: '', photographer: '', resolution: '' })
const selected = ref(null)
const index = computed(() => buildIndex(records.value))
const results = computed(() => searchRecords(index.value, records.value, filters.value.query, filters.value))

// spec §8 惰性加载：首屏只载最新年份分片，切到其他年份增量加载，「全部年份」才全量
async function ensureYear(year) {
  const key = String(year)
  if (!aggregations.value || !key || loadedYears.has(key)) return
  loadingMore.value = true
  try {
    const shards = await loadYearShards(aggregations.value, year)
    records.value = records.value.concat(shards)
    loadedYears.add(key)
  } finally {
    loadingMore.value = false
  }
}

async function ensureAllYears() {
  loadingMore.value = true
  try {
    records.value = await loadAllRecords(aggregations.value)
    for (const y of aggregations.value.years || []) loadedYears.add(String(y))
  } finally {
    loadingMore.value = false
  }
}

watch(
  () => filters.value.year,
  (y) => (y ? ensureYear(y) : ensureAllYears()),
)

onMounted(async () => {
  try {
    aggregations.value = await loadAggregations()
    const latest = (aggregations.value.years || []).at(-1)
    // 只改 filters.year，由上面的 watch 统一触发加载（避免显式调用导致同分片重复载入）
    filters.value.year = latest ? String(latest) : ''
  } catch (e) {
    error.value = `数据加载失败：${e.message}`
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <header class="site-header">
    <h1>Bing 壁纸索引</h1>
    <span v-if="aggregations" class="total">{{ aggregations.total }} 张 · 每日自动更新</span>
  </header>
  <FilterBar :aggregations="aggregations" v-model:filters="filters" />
  <p v-if="loading" class="status">加载中…</p>
  <p v-if="loadingMore" class="status">正在加载更多年份…</p>
  <p v-if="error" class="status error">{{ error }}</p>
  <WallpaperGrid :records="results" @select="selected = $event" />
  <WallpaperDetail v-if="selected" :record="selected" :records="records" @close="selected = null" />
  <footer class="site-footer">
    图片版权归 Microsoft 及原作者/图库所有，本站仅做元数据索引与链接。
  </footer>
</template>
```
（`WallpaperDetail` 在 Task 15 实现——本任务先创建其占位文件，内容为：
```vue
<script setup>
defineProps({ record: Object, records: Array })
const emit = defineEmits(['close'])
</script>
<template><div class="overlay" @click.self="emit('close')"><div class="modal"><p>{{ record.id }}</p><button @click="emit('close')">关闭</button></div></div></template>
```
Task 15 会完整重写它。）

`web/src/styles.css`:
```css
* { box-sizing: border-box; }
body { margin: 0; font-family: system-ui, -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif; background: #0e1116; color: #e6e8eb; }
.site-header { display: flex; align-items: baseline; gap: 12px; padding: 16px 20px; }
.site-header h1 { font-size: 20px; margin: 0; }
.total { color: #8a919c; font-size: 13px; }
.filter-bar { display: flex; flex-wrap: wrap; gap: 8px; padding: 0 20px 16px; position: sticky; top: 0; background: #0e1116; z-index: 5; }
.filter-bar .query { flex: 1 1 260px; }
.filter-bar input, .filter-bar select { background: #1a2029; color: inherit; border: 1px solid #2a3240; border-radius: 6px; padding: 8px 10px; font-size: 14px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 14px; padding: 0 20px 30px; }
.card { padding: 0; border: 1px solid #2a3240; border-radius: 10px; overflow: hidden; background: #1a2029; color: inherit; cursor: pointer; text-align: left; }
.card img { width: 100%; aspect-ratio: 16/9; object-fit: cover; display: block; }
.card .meta { display: flex; flex-direction: column; gap: 2px; padding: 8px 10px; font-size: 13px; }
.card .date { color: #8a919c; }
.card .title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.empty, .status { padding: 20px; color: #8a919c; }
.status.error { color: #e5726f; }
.site-footer { padding: 16px 20px 30px; color: #5c6470; font-size: 12px; }
.overlay { position: fixed; inset: 0; background: rgba(0,0,0,.7); display: flex; align-items: center; justify-content: center; z-index: 20; }
.modal { background: #161b22; border: 1px solid #2a3240; border-radius: 12px; max-width: 900px; width: min(92vw, 900px); max-height: 90vh; overflow: auto; padding: 16px; }
```

- [ ] **Step 2: 构建并用真实数据本地验证**

```bash
cd web && npm run build
cd .. && cp -r data web/dist/data
cd web && nohup npm run preview -- --port 4173 > /tmp/preview.log 2>&1 & sleep 2
curl -s http://localhost:4173/ | grep -o "<title>[^<]*</title>"
curl -s http://localhost:4173/data/aggregations.json | head -c 120
```
Expected: title 为「Bing 壁纸索引」；aggregations JSON 可访问。再用 Playwright 浏览器打开 `http://localhost:4173/`，用 accessibility snapshot（文本）确认：筛选栏 6 个控件存在、网格渲染出卡片（`browser_snapshot` 查看文本结构，不截图）。在搜索框输入「张家界」后 snapshot 中卡片数量减少且标题/描述含相关字。
验证完停掉 preview：`kill %1`

- [ ] **Step 3: 跑 vitest 确认无回归**

Run: `cd web && npm test`
Expected: 全过

- [ ] **Step 4: Commit**

```bash
git add web/
git commit -m "feat: 主界面——筛选栏、瀑布流与页脚

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 15: 详情弹层——大图、元数据、下载、同图跨市场

**Files:**
- Modify: `web/src/components/WallpaperDetail.vue`（整体替换 Task 14 占位）

**Interfaces:**
- Consumes: `imageUrl`/`RES_SUFFIX`（Task 13）、record schema（Task 4）
- Produces: props `{record: object, records: array}`，emits `close`；Esc 关闭；下载链接仅列出 `resolutions` 为 true 的档位

- [ ] **Step 1: 完整实现**

`web/src/components/WallpaperDetail.vue`:
```vue
<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { RES_SUFFIX, imageUrl } from '../api'

const props = defineProps({ record: Object, records: Array })
const emit = defineEmits(['close'])

const picked = ref('')
// 只暴露用户可选档位（thumb 是列表缩略图专用，spec §6.4 禁止展示），并按 uhd>fhd>hd 排序
const available = computed(() => Object.keys(RES_SUFFIX).filter((k) => props.record.resolutions?.[k] === true))
const viewRes = computed(() => picked.value || available.value[0] || 'fhd')
const siblings = computed(() =>
  props.records.filter((r) => r.imageKey && r.imageKey === props.record.imageKey && r.id !== props.record.id),
)
const viewSrc = computed(() => imageUrl(props.record.urlbase, RES_SUFFIX[viewRes.value] || '_1920x1080.jpg'))
const RES_LABEL = { uhd: '4K UHD (3840×2160)', fhd: '1920×1080', hd: '1366×768' }

function onKey(e) {
  if (e.key === 'Escape') emit('close')
}
onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <div class="overlay" @click.self="emit('close')">
    <div class="modal">
      <button class="close" aria-label="关闭" @click="emit('close')">✕</button>
      <img class="hero" :src="viewSrc" :alt="record.title || record.desc" />
      <div class="res-switch" v-if="available.length">
        <button v-for="k in available" :key="k" :class="{ active: k === viewRes }" @click="picked = k">
          {{ RES_LABEL[k] || k }}
        </button>
      </div>
      <h2>{{ record.title || record.desc }}</h2>
      <dl class="facts">
        <dt>日期</dt><dd>{{ record.date }}（{{ record.market }}）</dd>
        <dt v-if="record.location.length">地点</dt><dd v-if="record.location.length">{{ record.location.join(' · ') }}</dd>
        <dt v-if="record.region">国家/地区</dt><dd v-if="record.region">{{ record.region }}</dd>
        <dt v-if="record.photographer">摄影师</dt><dd v-if="record.photographer">{{ record.photographer }}</dd>
        <dt v-if="record.gallery">图库</dt><dd v-if="record.gallery">{{ record.gallery }}</dd>
      </dl>
      <div class="actions">
        <a v-for="k in available" :key="k" :href="imageUrl(record.urlbase, RES_SUFFIX[k] || `_${k}`)"
           target="_blank" rel="noopener">下载 {{ RES_LABEL[k] || k }}</a>
        <a v-if="record.copyrightlink" :href="record.copyrightlink" target="_blank" rel="noopener">背后故事 ↗</a>
      </div>
      <div v-if="siblings.length" class="siblings">
        <h3>同图其他市场</h3>
        <button v-for="s in siblings" :key="s.id" @click="$emit('select-sibling', s)">
          {{ s.market }} · {{ s.date }} · {{ s.title || s.desc }}
        </button>
      </div>
    </div>
  </div>
</template>
```
（`select-sibling` 事件需在 `App.vue` 的使用处补上：`<WallpaperDetail ... @select-sibling="selected = $event" />`——本任务 Step 2 一并修改。）

- [ ] **Step 2: App.vue 接线 + 样式补充**

在 `web/src/App.vue` 中把 `<WallpaperDetail v-if="selected" :record="selected" :records="records" @close="selected = null" />` 改为：
```html
<WallpaperDetail
  v-if="selected"
  :record="selected"
  :records="records"
  @close="selected = null"
  @select-sibling="selected = $event"
/>
```

在 `web/src/styles.css` 末尾追加：
```css
.modal { position: relative; }
.modal .close { position: absolute; top: 10px; right: 10px; background: #1a2029; color: inherit; border: 1px solid #2a3240; border-radius: 6px; padding: 4px 10px; cursor: pointer; }
.modal .hero { width: 100%; border-radius: 8px; }
.res-switch { display: flex; gap: 6px; margin-top: 10px; }
.res-switch button, .siblings button { background: #1a2029; color: inherit; border: 1px solid #2a3240; border-radius: 6px; padding: 6px 10px; cursor: pointer; font-size: 13px; }
.res-switch button.active { border-color: #4c8dff; color: #4c8dff; }
.modal h2 { font-size: 17px; margin: 14px 0 6px; }
.facts { display: grid; grid-template-columns: auto 1fr; gap: 4px 14px; margin: 0 0 12px; font-size: 14px; }
.facts dt { color: #8a919c; }
.facts dd { margin: 0; }
.actions { display: flex; flex-wrap: wrap; gap: 8px; }
.actions a { color: #4c8dff; text-decoration: none; border: 1px solid #2a3240; border-radius: 6px; padding: 6px 10px; font-size: 13px; }
.siblings { margin-top: 14px; }
.siblings h3 { font-size: 14px; color: #8a919c; }
.siblings button { display: block; width: 100%; text-align: left; margin-bottom: 6px; }
```

- [ ] **Step 3: 本地验证（日志/文本方式，不截图）**

```bash
cd web && npm run build && cd .. && cp -r data web/dist/data
cd web && nohup npm run preview -- --port 4173 > /tmp/preview.log 2>&1 & sleep 2
```
用 Playwright 浏览器打开 `http://localhost:4173/`：
1. snapshot 点击第一张卡片 → snapshot 确认弹层出现：大图 img、日期/摄影师字段、下载链接 `https://www.bing.com/th?id=...`、「背后故事」链接存在（有 copyrightlink 时）
2. snapshot 确认 res-switch 按钮只含 4K UHD / 1920×1080 / 1366×768 档，**无 thumb 档**
3. 点击「4K UHD」切换 → 用 `browser_network_requests` 确认发起了 `_UHD.jpg` 请求且返回 200
4. 按 Esc → snapshot 确认弹层关闭
5. 搜「张家界」→ 点开一张 → 确认无 JS console 错误（`browser_console_messages` level=error 应为空）
验证完 `kill %1`

- [ ] **Step 4: Commit**

```bash
git add web/
git commit -m "feat: 详情弹层——分辨率切换、下载直链、同图跨市场

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 16: GitHub Actions 工作流 + README

**Files:**
- Create: `.github/workflows/daily.yml`、`.github/workflows/backfill.yml`、`README.md`

**Interfaces:**
- Consumes: `python -m crawler.fetch_daily`（exit 1 = 核心市场失败）、`python -m crawler.backfill`、`web/dist` + `data/`
- Produces: 每日自动更新部署；手动回填入口

- [ ] **Step 1: 写工作流**

`.github/workflows/daily.yml`:
```yaml
name: daily-fetch
on:
  schedule:
    - cron: "0 22 * * *"   # UTC 22:00 = 北京时间次日 06:00
  workflow_dispatch:

permissions:
  contents: write
  pages: write
  id-token: write

concurrency:
  group: bing-wallpaper-deploy
  cancel-in-progress: false

jobs:
  fetch-and-deploy:
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt
      - name: 每日增量抓取（核心市场失败则红灯）
        run: python -m crawler.fetch_daily
      - name: 判断数据是否有变化（先暂存再看 diff——git diff 看不见未跟踪的新文件，年切换日靠它兜底）
        id: diff
        run: |
          git add -A data/
          if git diff --cached --quiet -- data/; then
            echo "changed=false" >> "$GITHUB_OUTPUT"
          else
            echo "changed=true" >> "$GITHUB_OUTPUT"
          fi
      - name: 提交数据
        if: steps.diff.outputs.changed == 'true'
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git commit -m "data: daily wallpaper update $(date -u +%F)"
          git pull --rebase origin main
          git push
      - uses: actions/setup-node@v4
        if: steps.diff.outputs.changed == 'true'
        with:
          node-version: "20"
          cache: npm
          cache-dependency-path: web/package-lock.json
      - run: npm ci
        if: steps.diff.outputs.changed == 'true'
        working-directory: web
      - run: npm run build
        if: steps.diff.outputs.changed == 'true'
        working-directory: web
      - run: cp -r data web/dist/data
        if: steps.diff.outputs.changed == 'true'
      - uses: actions/upload-pages-artifact@v3
        if: steps.diff.outputs.changed == 'true'
        with:
          path: web/dist
      - id: deployment
        uses: actions/deploy-pages@v4
        if: steps.diff.outputs.changed == 'true'
```

`.github/workflows/backfill.yml`:
```yaml
name: backfill
on:
  workflow_dispatch:
    inputs:
      check_resolutions:
        description: "验证分辨率可用性（约 45 分钟）"
        type: boolean
        default: true

permissions:
  contents: write
  pages: write
  id-token: write

concurrency:
  group: bing-wallpaper-deploy   # 与 daily.yml 共用，避免同时 push 冲突
  cancel-in-progress: false

jobs:
  backfill-and-deploy:
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt
      - name: 历史回填（含 mkt 预检，预检不过的市场自动剔除）
        run: |
          FLAG=""
          if [ "${{ inputs.check_resolutions }}" != "true" ]; then FLAG="--skip-resolution-check"; fi
          python -m crawler.backfill --data-dir data $FLAG
      - name: 判断数据是否有变化
        id: diff
        run: |
          git add -A data/
          if git diff --cached --quiet -- data/; then
            echo "changed=false" >> "$GITHUB_OUTPUT"
          else
            echo "changed=true" >> "$GITHUB_OUTPUT"
          fi
      - name: 提交数据
        if: steps.diff.outputs.changed == 'true'
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git commit -m "data: backfill $(date -u +%F)"
          git pull --rebase origin main
          git push
      - uses: actions/setup-node@v4
        if: steps.diff.outputs.changed == 'true'
        with:
          node-version: "20"
          cache: npm
          cache-dependency-path: web/package-lock.json
      - run: npm ci
        if: steps.diff.outputs.changed == 'true'
        working-directory: web
      - run: npm run build
        if: steps.diff.outputs.changed == 'true'
        working-directory: web
      - run: cp -r data web/dist/data
        if: steps.diff.outputs.changed == 'true'
      - uses: actions/upload-pages-artifact@v3
        if: steps.diff.outputs.changed == 'true'
        with:
          path: web/dist
      - id: deployment
        uses: actions/deploy-pages@v4
        if: steps.diff.outputs.changed == 'true'
```

- [ ] **Step 2: 校验 YAML 语法**

```bash
python - <<'EOF'
import yaml
for f in [".github/workflows/daily.yml", ".github/workflows/backfill.yml"]:
    yaml.safe_load(open(f))
    print(f, "OK")
EOF
```
Expected: 两个 OK（yaml 库缺失则先 `pip install pyyaml`——仅本地校验用，不进 requirements.txt）

- [ ] **Step 3: 写 README**

`README.md`:
```markdown
# Bing 壁纸索引

微软必应每日壁纸的元数据索引站：不只存壁纸，还结构化保存标题、拍摄地、摄影师、图库、日期和可用分辨率，支持按关键词、时间、市场、国家地区、摄影师、分辨率组合搜索。

**图片不做本地存储**，始终直链 Bing CDN。图片版权归 Microsoft 及原作者/图库所有，本站仅做元数据索引与链接。

## 在线访问

部署到 GitHub Pages 后填入：`https://<用户名>.github.io/<仓库名>/`

## 数据来源

- Bing 官方接口 `HPImageArchive.aspx`（免密钥，仅最近约 15 天，每日增量）
- [niumoo/bing-wallpaper](https://github.com/niumoo/bing-wallpaper) 的 `docs/images.json`（zh-cn 自 2023-02、en-us 自 2021-02 的历史回填）

## 目录结构

    crawler/   Python 抓取：每日增量 + 历史回填 + copyright 解析 + schema 校验
    data/      产物：data/{market}/{year}.json 分片 + aggregations.json（即站点 API）
    web/       Vue 3 + Vite 静态站：MiniSearch 浏览器内搜索

## 本地开发

    python3 -m venv .venv && source .venv/bin/activate
    pip install -r requirements-dev.txt
    python -m pytest tests/ -v          # 后端测试
    python -m crawler.fetch_daily       # 手动跑一次增量

    cd web && npm install && npm test   # 前端测试
    npm run dev                         # 本地预览（需先 cp -r data web/dist/data 或配代理）

## 自动更新

GitHub Actions 每日 UTC 22:00（北京时间 06:00）跑增量抓取，数据有变化时提交并部署 Pages。核心市场 zh-cn/en-us 失败会红灯；扩展市场（ja-jp、en-gb、de-de、fr-fr、ko-kr、zh-tw）尽力抓取，可在 `crawler/markets.py` 用 `EXTENDED_ENABLED = False` 关闭。

历史回填在 Actions 里手动触发 `backfill` workflow，或本地 `python -m crawler.backfill`。

## 扩展

- 新回填源：实现 `fetch() -> list[dict]`（字段同 `crawler/sources/niumoo_source.py` 输出），加进 `crawler/backfill.py` 的 `sources` 列表即可
- 内容搜索（Phase 2）：记录已预留 `tags` 字段，图像打标后回填即可被搜索
```

- [ ] **Step 4: Commit**

```bash
git add .github/ README.md
git commit -m "ci: 每日抓取与回填工作流、README

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 17: 上线与端到端验证（需涛总配合）

**Files:**
- Modify: 无新文件（远程仓库操作 + 线上验证）

**Interfaces:**
- Consumes: Task 1-16 全部产物
- Produces: 线上可访问的站点 + 每日自动更新生效

- [ ] **Step 1: 创建远程仓库并推送（需涛总确认仓库名与公开性）**

```bash
gh repo create bing-wallpaper --public --source=. --push
```
（若涛总想用别的名字/私有仓库，按其要求调整。）

- [ ] **Step 2: 启用 GitHub Pages（Actions 部署模式）**

```bash
gh api repos/{owner}/bing-wallpaper/pages -X POST -f build_type=workflow
```
（或网页：Settings → Pages → Source 选「GitHub Actions」。）

- [ ] **Step 3: 手动触发一次 daily workflow 验证全链路**

```bash
gh workflow run daily.yml && sleep 60 && gh run list --workflow=daily.yml --limit 1
gh run watch $(gh run list --workflow=daily.yml --limit 1 --json databaseId -q '.[0].databaseId')
```
Expected: run 成功（green）。**mkt 验证（spec §7.2 风险点）**：
```bash
git pull
ls data/
head -c 400 data/ja-jp/2026.json 2>/dev/null || echo "ja-jp 当日无数据，属正常"
python - <<'EOF'
import json, glob, re
for f in glob.glob("data/*/*.json"):
    for r in json.loads(open(f).read())[:3]:
        if r["market"] in ("zh-cn", "en-us"):
            continue  # 核心市场已由本地回填验证
        code = r["market"].upper()  # 如 ja-jp -> JA-JP
        assert re.search(rf"_{code}\d+", r["urlbase"]), (f, r["urlbase"])
print("mkt check OK")
EOF
```
Expected: 扩展市场（若有数据）urlbase 均含各自市场后缀（如 `_JA-JP123`）；若仍全是 `_ZH-CN`，说明 Actions 环境 mkt 也未生效 → 停下来向涛总报告，改为逐市场域名方案（`cn.bing.com`/`www.bing.com`/`jp.bing.com`…）后再继续

- [ ] **Step 4: 线上站点验证（文本方式）**

```bash
PAGES_URL=$(gh api repos/{owner}/bing-wallpaper/pages -q '.html_url')
echo "$PAGES_URL"
curl -s "$PAGES_URL" | grep -o "<title>[^<]*</title>"
curl -s "$PAGES_URL/data/aggregations.json" | python3 -c "import json,sys; d=json.load(sys.stdin); print('total:', d['total'], 'markets:', d['markets'])"
curl -s -o /dev/null -w "%{http_code}" "$PAGES_URL/data/zh-cn/2023.json"
```
Expected: title 正常；aggregations total 与仓库一致；zh-cn 2023 分片 200。再用 Playwright 打开线上地址，snapshot 确认筛选栏与网格渲染，搜「张家界」出结果，console 无 error。

- [ ] **Step 5: 确认次日自动运行**

告诉涛总：次日起每天北京时间 06:00+ 会自动跑。可用 `gh run list --workflow=daily.yml` 随时检查。项目交付完成。

---

## 计划自审记录（写计划时已核）

1. **Spec 覆盖**：§5 市场分级→Task 1/11；§6 数据模型→Task 4/7；§6.3 解析→Task 2/3；§6.4 分辨率→Task 6；§7.1 增量→Task 11；§7.2 回填+source-adapter+mkt 风险+日期基准+mkt 预检→Task 9/10/12/17；§8 前端（含惰性加载）→Task 13/14/15；§9 Actions→Task 16/17；§10 错误处理→Task 5/6/10/11 内嵌；§11 测试→各任务 TDD；§12 YAGNI 边界未越界（未下载图片、未做用户系统、tags 恒空）
2. **占位符扫描**：无 TBD/TODO；所有代码步骤含完整代码
3. **类型一致性**：`build_record`（Task 10 定义，Task 11 消费）；raw 记录 7 字段（Task 5 定义，Task 9/10/11 消费）；`years_by_market`（Task 7 生成，Task 13 消费）；`make_record` fixture（Task 4 入 conftest，Task 7 复用）；`RESOLUTION_SUFFIXES` 四键（Task 6/13/15 一致）
4. **Review Focus**：八类输入均已钉进对应任务测试（见首节标注）

## 对抗式审查修订记录（2026-10-06）

独立审查代理以真实执行方式（计划代码原样组装跑 pytest/vitest、真实回填 smoke、真实数据对比）发现 6 P1 + 12 P2，已全部修订入计划：

| # | 级别 | 缺陷 | 修订 |
|---|---|---|---|
| 1 | P1 | niumoo date 与 Bing startdate 系统性 +1 天，合并永不交集、产出重复/未来日期记录 | Task 9 源头归一化 `date-1`+去重+丢未来；Task 12 smoke 加零重复/零未来断言；spec §7.2 补条款 |
| 2 | P1 | mkt 污染数据先 commit 后验证 | Task 12 新增 Step 0 `verify_mkt` 预检，未过则强制 `--markets zh-cn,en-us`；Task 10 实现 verify_mkt + `--markets` |
| 3 | P1 | Task 6 测试三处自相矛盾（KeyError/status_code/异常类型） | 测试与实现同步修正，补 OSError 兜底 |
| 4 | P1 | 搜索 OR 回退在空结果上过滤（死代码） | 回退分支改从原始 records 过滤；测试改用真正 AND-miss 的查询 |
| 5 | P1 | `git diff --quiet` 看不见未跟踪文件，年切换日静默丢数据 | daily/backfill 均改 `git add -A` + `git diff --cached --quiet` |
| 6 | P1 | 详情弹层混入 thumb 档（404 按钮） | `available` 改按 `RES_SUFFIX` 白名单生成，默认档取可用优先级 |
| 7-18 | P2 | git 未 init 兜底、坏记录毒化市场/回填、HEAD 网络抖动固化 false、region 词边界+否定短语、解析器嵌套括号/纯日期、空转测试、backfill 不部署+并发保护、全量加载违背惰性 spec、niumoo 数据清洗、smoke 指标不足 | 分别落入 Task 1/2/3/5/6/9/10/11/13/14/16 修订 |
