# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目定位

Bing 每日壁纸的元数据索引站（仅索引元数据，**图片永不落地**，直链 Bing CDN）。Python 抓取 + 分片 JSON 数据 + Vue 3 静态站，GitHub Actions 每日自动抓取并部署到 Pages：https://imhet.github.io/bing-wallpaper-atlas/

当前规模：~11250 条记录 / 6 市场 / ~6770 图组（en-us 深史至 2010，ja/de/fr/gb 2024 起；深史由 npanuhin 归档 + 镜像绝对 URL 补齐）。

## 常用命令

```bash
# Python 测试（venv 由 uv 管理——系统 Python 3.14 的 ensurepip 损坏，不要用 python3 -m venv）
./.venv/bin/python -m pytest                        # 全部
./.venv/bin/python -m pytest tests/test_merge.py    # 单文件
./.venv/bin/python -m pytest tests/test_merge.py::test_name  # 单用例

# venv 重建（如需）
uv venv --clear .venv --python 3.12 && uv pip install -p .venv/bin/python -r requirements-dev.txt

# 前端测试 / 构建 + 本地预览
npm run test --prefix web
npm run build --prefix web && cp -r data web/dist/data && npm run preview --prefix web
# 注意：vite build 实测不清空 dist/（残留旧文件），数据用 cp -r data/. web/dist/data/（`/.` 形式防目录嵌套）；
# 长时间运行的 preview server 在重建 dist 后会持有旧 inode（所有请求 404 回落 index.html），重kill 再跑 E2E

# 每日增量 / 历史回填
./.venv/bin/python -m crawler.fetch_daily --data-dir data
./.venv/bin/python -m crawler.backfill --data-dir data [--markets zh-cn] [--skip-resolution-check]
```

本机直连 github.com 主站常超时（api.github.com 可直连）：`git push`、device 授权等操作挂 `HTTPS_PROXY=http://127.0.0.1:1087`。

## 架构

### 数据流水线（crawler/）

```
sources/niumoo_source.py      历史源：niumoo 仓库 images.json（date 系统性 +1 需减一）
sources/npanuhin_source.py    深史源：npanuhin 归档（2010-2023，镜像绝对 URL，无 OHR ID）
sources/bing_api_source.py    增量源：HPImageArchive.aspx 近 8 天 × 8 市场
        ↓
backfill.py / fetch_daily.py  build_record() 拼 15 字段记录：
                              copyright_parser 解析 ©（永不抛异常；无 © 块 = 源无地点结构，
                              location 留空由词典挖填，返回 has_copyright）
                              regions.py 做国家归一（COUNTRY_ALIASES + 否定短语）
                              geo_enrich.extract_locations 词典挖地名（title+desc，具体地名
                              优先/国家殿后，上限 5）写入 location + 多语言地名 tags
                              content_tags.py 内容打标：VLM 优先，降级本地 CLIP
        ↓
merge.py                      merge_records()：源优先级非空覆盖；(market,date) 冲突抛错
        ↓
storage.py                    data/{market}/{year}.json 分片 + aggregations.json
        ↓
.github/workflows/            daily.yml（cron UTC 22:00，push 不触发；纯前端改动上线要
                              gh workflow run daily.yml -f force_deploy=true）与 backfill.yml
                              concurrency 组 bing-wallpaper-deploy，抓取→提交→构建→部署 Pages
```

存量修复脚本（幂等，数据问题复发时重跑）：`crawler/fix_locations.py`——无版权结构的记录四线挖 location：自身 title+desc → 同图组兄弟市场继承 → content_tags VLM 概念 → region 国家兜底（两趟：先全库后组内桥接）。

纯前端改动上线用 `gh workflow run daily.yml -f force_deploy=true`（数据无变化时也能部署）。

### 前端（web/）

Vue 3 + MiniSearch，无路由无状态库。`api.js` 的 `fetchJSON` 对 `./data/` 走 **jsDelivr 分流**（HEAD 预检可达才走，失败降级 Pages；daily.yml 部署后 `crawler/purge_jsdelivr.py` 主动刷缓存）。`public/sw.js` Service Worker：assets/模型 cache-first、数据 SWR、离线兜底；**E2E 全局 `serviceWorkers: 'block'`**（SW 内 fetch 不走 page.route，开着所有 mock 失效）。详情弹层「相似的图」=`semantic.js similarImages` 图向量余弦近邻（只拉图向量不碰语言模型）。`?pic=<id>` 分享直达详情弹层——**id 自含市场+年份，快速通道只拉对应年分片即开弹层**（不等全量；失败静默落全量兜底）。收藏有导出/导入（favorites.js，v1 JSON）。分片仍按年惰性加载（App.vue 的 `watch(filters.year)` 驱动）。`vite.config.js` 设 `base: './'` 以兼容 Pages 子路径。

**结果口径的唯一入口**：App.vue `fusedResults(query, filters)`——关键词 + 语义融合的唯一入口，结果列表与分面计数（`facets.js` 的 `computeFacets(search, filters)`，search 由调用方传入）都从这里走；分面计数若不走同一口径，语义扩召的查询（关键词层 2 条、语义 200 张）面板会全是 0/1。

**同图去重的三层口径**（键 = `recordKey`：imageKey 优先，否则 urlbase 剥市场后缀）：
- 首页网格 `uniqueResults`：dedupeByUrlbase（代表 zh-cn 优先）后**按代表日期重排**——代表的日期比组内最晚记录早 1~2 天，不重排会「旧图插队」（324 处）
- 更新日志 `updates.js groupByDate`：两趟分组，图组归入最早「本体日」（en-us/ja-jp 时区晚 1~2 天不是新图），组内再 dedupeByUrlbase
- 沉浸模式列表跟随当前视图：浏览 = uniqueResults、收藏 = favoriteRecords、更新日志 = groupByDate 平铺

**沉浸观赏（components/ImmersiveViewer.vue）**：详情弹层「⛶ 沉浸观赏」进入。黑底大图 `fitScale.js` 等比放大尽量铺满（cover 裁切超 20% 回退 contain，resize 重算）；切换必须等新图加载完成才替换 `shownSrc`（浏览器对改 src 的 img 保留旧像素——直链切换会滞留旧图，快连按看似「没动」），未预加载的慢图显示中央 spinner；收藏三通道（双击图片 / ↑ 收藏 ↓ 取消 / 顶排按钮，心形动画反馈）；UI 空闲 3 秒连光标一起淡出；Esc 在 **capture 阶段接管并 stopPropagation**（弹层的 Esc 关闭收不到，层级靠这个维持）；进入时 `requestFullscreen` 跟随（失败静默降级）。弹层顶排 `.modal-top` 与沉浸顶排 `.viewer-top` 均为 flex 按钮排——新增按钮**绝不能**再挂 `position: absolute`（会被拽出 flex 流叠在一起，E2E 有 boundingBox 不相交断言）。

**语义检索（semantic.js / semantic-engine.js）**：不受关键词命中的限制，按画面内容检索。
构建期用 Chinese-CLIP 图像塔把每个图组封面编成 512 维 int8 向量（`crawler/semantic_index.py` → `data/sem/{year}.bin`，增量构建：已编码的图组直接复用，CI 每天只编新增的 1~2 张）。浏览器端用 bge-small-zh int8 ONNX（`data/sem/bge/`）把查询映射到概念表（`content_tags` 频次≥5 的词），再用预计算的 CLIP 概念向量给图打分，与关键词结果做 RRF 融合（`rrfFuse`，语义只取前 200 名参与，否则结果数会变成全库大小）。模型 23MB + 向量 7MB 在空闲时后台加载，失败静默退回纯关键词。100 查询评估集：nDCG@10 55.3% → 63.3%，零结果率 14% → 0%。概念分片只在打标词表明显变化时重建：`--concepts --bge-onnx <onnx> --bge-tokenizer <dir>`。**向量可能滞后数据一天**：daily 里 semantic_index 是 continue-on-error，新图当天可能没向量（相似图区块对它隐藏、语义检索召回不到），次日 workflow 重试补编——属预期不是 bug。**地理约束 `semantic.js geoFilterSemScores`**：CLIP 概念不懂国别，「中国的秋景」关键词层零结果、语义前排会混进日本图——查询段完整等于某 region 值时（`search.js extractGeoTerms`），语义分数 region 匹配 ×3 / 冲突 ×0.05 / null 保持。

**搜索（search.js）是本项目最精巧的部分，改动前先读懂**：`tokenize()` 把中文切成「单字 + 相邻二元组」（`中国雪山` → `中/中国/国/国雪/雪/雪山/山`）——单字负责字面召回，二元组让 AND 匹配到连续词语，否则搜「中国」会被「国家公园…框景中」这类字符共现误报。AND 无命中时回退到**词组级** OR（用查询选项 `tokenize: () => orTokens` 覆盖，防止 join 后被重切成单字）。关键词层有单槽缓存（`keywordStage`，index/records 引用失效）——分面 6 维对同一 query 重查不重复打分；查询输入在 FilterBar 做 200ms 防抖。

## 领域规则（不读代码会踩的坑）

- **mkt 预检（verify_mkt）**：Bing 按网络位置覆盖 `mkt` 参数的 feed。任何环境跑回填前必须预检，不过的市场必须剔除——ko-kr、zh-tw 连美国出口都被路由污染（线上无此两市场数据是预期行为），扩展市场靠 urlbase 里的 `_JA-JP123` 后缀正则验证
- **niumoo 源的 date 系统性 +1 天**：必须减一归一化再入库（`_shift_date`），(market,date) 去重、未来日期丢弃
- **记录 schema**（schema.py）：15 字段 `additionalProperties: false`，id 形如 `zh-cn-2023-10-05`
- **aggregations.json 无时间戳**：数据不变时重新生成应产生零 git diff，别引入易变字段
- **分辨率探测**（resolutions.py）：uhd/fhd/hd/thumb 四档 HEAD 探测是回填最耗时的一段（interval 0.2s）；已带 resolutions 的记录 skip-guard 会跳过
- 前端详情弹层的分辨率按钮按 `RES_SUFFIX` 白名单生成，thumb 只做网格缩略图，不进弹层
- **多语言地名词典**（geo_enrich.py + geo_aliases.json，302 组）：文本命中任一写法即把「规范中文名 + 全组别名」写入 tags，实现跨语言搜索（优胜美地=yosemite=ヨセミテ）。长尾地名搜不到时：词典加条目 → `python -m crawler.geo_enrich --data-dir data` 重跑，**搜索端零改动**；拉丁别名 `\b` 词边界防误报（comparison 不中 paris）。词典手术红线：超短拉丁别名（us/uk）不收（site.co.uk 全体误挂）、人名疑似不收（'jordan' 是摔跤手）、否定上下文 `_NEGATIVE_CONTEXT` 定点修类比误报（富士山文类比勃朗峰/法国、Fuji 苹果品种）
- **location 是挖出来的不是解析出来的**：镜像深史 desc 无 © 块（parse_copyright 返回 has_copyright=False）= 源不提供地点结构，location 由 `extract_locations` 从 title+desc 词典挖掘 + fix_locations 四线兜底（见流水线段）；覆盖 ~91%，剩余孤图文本层无线索属预期

## 测试约定

后端 pytest（tests/ 与 crawler/ 镜像分文件，`conftest.py` 的 `make_record` fixture 供 15 字段合法记录）；前端 vitest（`search.test.js` 的三条 mock 记录专为搜索误报场景设计——拱门国家公园记录用于验证「中国」不再误报）。改搜索逻辑必须先跑 `npm run test --prefix web`。
