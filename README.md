# Bing 壁纸图集（bing-wallpaper-atlas）

微软必应每日壁纸的元数据索引站：不只存壁纸，还结构化保存标题、拍摄地、摄影师、图库、日期和可用分辨率，支持按关键词、时间、市场、国家地区、摄影师、分辨率组合搜索。

**图片不做本地存储**，始终直链 Bing CDN。图片版权归 Microsoft 及原作者/图库所有，本站仅做元数据索引与链接。

## 在线访问

**https://imhet.github.io/bing-wallpaper-atlas/**

## 为什么做

Bing 每日壁纸每天零点上新、第二天零点下线，官方不提供任何归档入口，接口也只保留最近 15 天——哪天没截图，那张图连同它的拍摄地、摄影师和背后故事就再也找不回来了。

这个项目把历年的壁纸元数据全部留了下来，并让它们**可搜索**：11,000+ 条记录、6 个市场、6,700+ 张唯一图（en-us 深史追溯至 2010 年），全部数据只有几 MB。真正的资产不是图，是那些结构化的元数据。

背景故事与技术细节见[项目自述文章](docs/2026-10-12-bing-wallpaper-atlas-story.md)。

## 特性

### 搜索

- **语义检索**：浏览器内跑 bge-small-zh 向量模型 + 构建期 Chinese-CLIP 图像向量，按画面内容检索而非关键词命中——搜「秋天的森林」能召回文字里没有这些字的图，与关键词结果融合排序；带地理限定词（「**中国的**秋景」）时语义候选按国家过滤，不让邻国图混进前排
- **组合筛选**：市场 × 年份 × 国家地区 × 摄影师 × 分辨率，分面联动计数（各下拉的数字按「其余筛选条件下的分布」动态计算，与搜索结果严格同口径）
- **中文搜索**：自研 tokenizer 把查询切成「单字 + 相邻二元组」——单字保召回、二元组防误报（搜「中国」不会命中「国家公园……框景**中**」），AND 全落空回退词组级 OR
- **跨语言搜索**：302 组多语言地名词典（优胜美地 = yosemite = ヨセミテ = 優勝美地），搜任何一种写法都能召回整组；命中高亮同样跨语言桥接
- **行政区划层级**：347 条「子地名 → 父行政区」映射，搜「湖南」召回张家界，哪怕文字里从没出现过「湖南」
- **画面内容标签**：每张图由 **VLM（glm-5.3-flash）优先、本地 CLIP（ViT-B-16）兜底** 双引擎打上画面标签——「乐山大佛」「云冈石窟」「红墙」「烟花」这类文字描述里根本没有的词直接命中。VLM 是开放理解，专名级标签不受词表限制；失败自动降级 CLIP，不阻塞每日更新

### 体验

- **沉浸观赏**：全屏黑底大图等比放大铺满（构图裁切超 20% 自动收敛），← → / 拖拽滑动切换、双击或 ↑↓ 收藏（心形动画反馈）、空闲 3 秒界面与光标一起淡出、自动进入浏览器全屏
- **本地收藏**：喜欢的图存进浏览器（localStorage），跨会话保留
- **更新日志**：按发布日期倒序浏览每日上新，同图多市场/跨时区自动去重，只看真新图
- **同图跨市场去重**：全球各市场发同一张图（11,000+ 条记录实际 6,700+ 张不同图），网格只显示一次，详情页可切换市场版本对比元数据
- **地点信息**：91% 的图有结构化地点（多语言词典从描述挖掘 + 同图组跨市场继承 + VLM 标签兜底），详情页一键跳转 Google Maps
- **详情弹层**：背后故事、摄影师/图库、可点击搜索的标签（地点 + 画面）、多档分辨率直链
- **URL 状态同步**：搜索词与筛选条件写进 URL，结果页可直接分享/收藏直达
- **渐进渲染**：首屏只等主视角市场分片即刻出图，其余分片后台补齐，滚动到底自动追加；暗色模式三态、移动端适配、随机看看、零结果智能建议

## 数据来源

- Bing 官方接口 `HPImageArchive.aspx`（免密钥，近 8 天 × 8 市场，每日增量；接入前做 mkt 预检，被 Bing 路由污染的市场自动剔除）
- [niumoo/bing-wallpaper](https://github.com/niumoo/bing-wallpaper) 的 `docs/images.json`（zh-cn/en-us 近年全历史）
- [npanuhin/bing-wallpaper](https://github.com/npanuhin/bing-wallpaper)（en-us 深史 2010-2023：归档元数据 + 镜像绝对 URL，老图无多档分辨率变体）

当前规模：zh-cn / en-us 全量深史，de-de / en-gb / fr-fr / ja-jp 自 2024 年起。

## 架构

```
sources/niumoo_source.py      历史源：niumoo 仓库 images.json（多年全历史）
sources/npanuhin_source.py    深史源：npanuhin 归档（2010-2023，镜像绝对 URL）
sources/bing_api_source.py    增量源：HPImageArchive.aspx 近 8 天 × 8 市场
        ↓
backfill.py / fetch_daily.py  build_record() 拼 15 字段记录：
                              copyright_parser 解析 ©（摄影师/图库/地点）
                              regions.py 国家归一
                              geo_enrich 多语言地名 tags + location 词典挖掘
        ↓
content_tags.py               内容打标：VLM（glm-5.3-flash）优先，降级本地 CLIP ViT-B-16
semantic_index.py             Chinese-CLIP 图像向量（语义检索用，增量构建）
        ↓
merge.py / storage.py         data/{market}/{year}.json 分片 + aggregations.json
        ↓
.github/workflows/daily.yml   每天 UTC 22:00：抓取 → 打标 → 提交 → 构建 → 部署 Pages
```

    crawler/   Python 抓取与数据流水线（含 geo 词典、内容打标、语义向量构建）
    data/      产物：分片 JSON + aggregations.json + 语义向量（即站点 API）
    web/       Vue 3 + Vite 静态站：MiniSearch + 浏览器内语义检索，零后端
    tests/     后端 pytest + 前端 vitest + Playwright E2E + 搜索黄金集

## 扩展数据

- **加地名/别名**：编辑 `crawler/geo_aliases.json`（区划层级加 `crawler/geo_hierarchy.json`），重跑 `python -m crawler.geo_enrich --data-dir data`，搜索端零改动
- **加画面概念词表**（仅影响 CLIP 兜底引擎）：编辑 `crawler/content_vocab.json`，重跑 `python -m crawler.content_tags --force`
- **新回填源**：实现 `fetch() -> list[dict]`（字段同 `crawler/sources/niumoo_source.py` 输出），加进 `crawler/backfill.py` 的 `sources` 列表即可

## 本地开发

    uv venv .venv --python 3.12 && uv pip install -p .venv/bin/python -r requirements-dev.txt
    ./.venv/bin/python -m pytest tests/ -v     # 后端测试
    ./.venv/bin/python -m crawler.fetch_daily  # 手动跑一次增量（扩展市场会先做 mkt 预检，本地网络受限时自动跳过未通过的市场）

    cd web && npm install && npm test   # 前端测试（含搜索黄金集）
    npm run e2e                         # Playwright E2E
    npm run build && cp -r ../data/. dist/data && npm run preview   # 本地预览

## 自动更新

GitHub Actions 每日 UTC 22:00（北京时间 06:00）跑增量抓取与内容打标，数据有变化时提交并部署 Pages。核心市场 zh-cn/en-us 失败会红灯；打标步骤失败不阻塞（VLM 降级 CLIP，次日自动补打）。历史回填在 Actions 里手动触发 `backfill` workflow，或本地 `python -m crawler.backfill`。
