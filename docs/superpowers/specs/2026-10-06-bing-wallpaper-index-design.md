# Bing 壁纸索引站 · 设计文档

- 日期：2026-10-06
- 状态：已与需求方（涛总）逐节确认
- 项目路径：`bing-wallpaper/`（新项目）

## 1. 背景与目标

Bing 每日壁纸只有图片本身在流传，现有的归档项目（如 niumoo/bing-wallpaper）把标题、地点、摄影师、图库全部挤在一个非结构化的版权字符串里，无法按条件检索。用户想找「张家界的壁纸」时无法定位到具体日期的图。

**目标**：建一个 Bing 每日壁纸的元数据缓存 + 索引站：

1. 结构化存储壁纸元数据：标题、拍摄地、摄影师、图库、日期、可用分辨率、故事链接
2. 支持按关键词、时间、国家地区、摄影师、市场、分辨率组合筛选/搜索
3. 公开静态站（GitHub Pages），GitHub Actions 每日自动更新，零服务器零数据库
4. 不下载壁纸本体，图片始终直链 Bing CDN / 归档仓库，规避存储与版权风险
5. 为 Phase 2 内容搜索（搜「雪山」出有雪山的图）预留 `tags` 字段，本期不实现

**非目标（本期明确不做）**：

- 不下载/转存图片本体
- 不做用户系统、收藏、评论
- 不回填 2021-02（en-us）/ 2023-02（zh-cn）之前的历史（留 source-adapter 口子，后续可加源）
- 不实现基于图像识别的内容搜索（只预留字段）

## 2. 已确认的关键决策

| 决策点 | 结论 | 理由 |
|---|---|---|
| 使用形态 | 公开静态站 + GitHub Actions 自动更新 | 免费、数据天然公开、无运维 |
| 市场覆盖 | 多市场，初始 8 个（见 §5） | 不同市场标题/描述不同，元数据更丰富 |
| 历史回填 | zh-cn/en-us 全量回填（受归档源限制），其余市场从今开始 | 平衡覆盖面与实现难度 |
| 数据组织 | 分片 JSON + 前端内存搜索（MiniSearch） | 量级（约 1 万条级）完全够用，极简 |
| 抓取语言 | Python | 数据处理方便，Actions 零配置 |
| 前端栈 | Vue 3 + Vite | 轻量、构建产物小 |

## 3. 数据源（已实测验证）

1. **Bing 官方接口** `https://www.bing.com/HPImageArchive.aspx?format=js&idx=0&n=8&mkt={market}`
   - 免密钥，返回 title / copyright（地点+摄影师+图库）/ startdate / urlbase / copyrightlink / quiz
   - **只能取最近约 15 天**（idx 超界会被钳制回最新，已实测）
   - `urlbase` 形如 `/th?id=OHR.DanxiaLandform_ZH-CN2386060246`，追加 `_UHD.jpg` / `_1920x1080.jpg` / `_1366x768.jpg` 后缀即得不同分辨率；缩略图可加 `w=`/`h=` 查询参数动态缩放
   - 每个请求取 n=8（最大窗口），为漏抓留冗余
2. **niumoo/bing-wallpaper 仓库** `docs/images.json`（结构化数组，字段 date/region/url/desc）
   - 实测覆盖：en-us 2021-02-01 起共 2074 天；zh-cn 2023-02-04 起共 1388 天
   - 缺 title/copyrightlink，靠字段级互补合并从接口补齐（历史记录补不到的就置空）

## 4. 总体架构

```
GitHub Actions（每日定时 UTC 22:00 / 手动）
   │                    │
   │ 跑抓取              │ 部署 Pages
   ▼                    ▼
crawler/ (Python)  ──写──▶  data/ (JSON 分片，git 提交)      web/ (Vue3+Vite 静态站)
```

- `crawler/`：每日增量 + 一次性回填 + 校验。只抓元数据
- `data/`：抓取产物，按市场按年分片，git 提交（数据变化全程可追溯），部署时复制进站点产物
- `web/`：浏览器端完成搜索与筛选，部署到 GitHub Pages

## 5. 市场清单（配置驱动，分优先级）

定义于 `crawler/markets.py`，分两级（需求方确认：cn/en 优先，其余市场优先级放低）：

| 级别 | 市场 | 策略 |
|---|---|---|
| 核心市场 | `zh-cn`, `en-us` | 每日必抓；抓取失败 → Actions 红灯告警；有历史回填数据 |
| 扩展市场 | `ja-jp`, `en-gb`, `de-de`, `fr-fr`, `ko-kr`, `zh-tw` | 核心市场全部成功后才抓；单市场失败只记日志、不告警；配置开关可整体启停 |

- 数据文件内 market 一律小写（`zh-cn`）；请求 Bing 接口时转大写参数（`mkt=zh-CN`）
- zh-cn / en-us 有历史回填数据；扩展市场从项目上线当天开始积累
- 每日流程：先抓核心市场，任何核心市场失败则重试后仍失败 → 告警并跳过扩展市场；核心成功 → 继续扩展市场，扩展市场失败不影响本次部署

## 6. 数据模型

存储布局：`data/{market}/{year}.json`，每个文件是按 date 升序的记录数组；另加 `data/aggregations.json`。

每条记录：

```jsonc
{
  "id": "zh-cn-20231005",                  // 主键 = 市场 + 日期（同市场一天一图）
  "market": "zh-cn",
  "date": "2023-10-05",                     // 来自接口 startdate（当地时间）
  "imageKey": "ZhangjiajieMist",            // 从 urlbase 提取，跨市场关联同一张图
  "title": "云海仙境",
  "desc": "张家界云海 (© Li Hua/Getty Images)",  // 原始 copyright 字符串，解析兜底
  "location": ["张家界", "湖南省", "中国"],   // 解析出的地点链（由近及远）
  "region": "中国",                          // 国家/地区，筛选维度；解析失败置空
  "photographer": "Li Hua",                 // 解析失败置空
  "gallery": "Getty Images",                // 图库；无则置空
  "copyrightlink": "https://...",           // 故事/背景链接；历史缺失置空
  "quiz": "https://...",                    // 有则存，无则置空
  "resolutions": {"uhd": true, "fhd": true, "hd": true},  // 入库时 HEAD 验证
  "tags": []                                // Phase 2 内容搜索预留，本期恒为空数组
}
```

关键规则：

1. **imageKey 提取**：对 urlbase 应用正则 `OHR\.([A-Za-z0-9]+?)_[A-Z]{2}-[A-Z]{2}\d+$`，取捕获组。无法提取时置空（不阻塞入库）
2. **urlbase 存储**：存 Bing 相对路径（不含分辨率后缀），前端按需拼分辨率与缩略参数，不受 Bing 域名变化影响
3. **copyright 解析**（`crawler/copyright_parser.py`）：
   - 括号内 `© 摄影师/图库`：正则 `©\s*(?P<photographer>[^(/]+)(?:\s*/\s*(?P<gallery>.+?))?\s*\)$`；无 `/` 时 gallery 置空
   - 地点链：中文市场按 `，`/`,` 切分括号外文本；尾部若匹配日期模式（如 `2022年6月15日`）先剥离
   - region：地点链末项匹配国家/地区词表（`crawler/regions.py`，中文+英文对照）；非中文市场对括号外全文做词表匹配（英文 copyright 是句子不是逗号链）；都失败则 region 置空
   - 任何一步失败都**不丢数据**：保留原始 `desc`，对应字段置空并记日志
4. **分辨率验证**：候选后缀清单 `[_UHD, _1920x1080, _1366x768]`（映射 uhd/fhd/hd，配置驱动）。对每个候选发 HEAD 请求，200 才置 true。回填一次性约 1 万个请求（限速 5 req/s，约 35 分钟，失败清单可重跑）；每日增量约 10 个
5. **aggregations.json**：每次写数据后重新生成 `{photographers: [], regions: [], years: [], markets: []}`（photographers/regions 带出现次数），前端筛选下拉直接消费

## 7. 抓取流程

### 7.1 每日增量 `crawler/fetch_daily.py`

1. 逐市场请求 `HPImageArchive.aspx?format=js&idx=0&n=8`（8 天窗口容忍漏抓）
2. 按 `id` 与已有数据比对，仅写入新记录
3. 新记录：copyright 解析 → 分辨率 HEAD 验证 → 就地更新 `{market}/{year}.json`（保持 date 升序）
4. 重新生成 `aggregations.json`
5. 数据无变化时不产生 git diff（Actions 据此跳过部署）

### 7.2 历史回填 `crawler/backfill.py`（一次性，可重跑）

- **Source-adapter 设计**：每个回填源实现 `fetch() -> list[标准记录]`，本期两个：
  - `NiumooSource`：拉取 images.json（zh-cn 1388 天 + en-us 2074 天）
  - `BingApiSource`：接口本身（补 title/copyrightlink 等富字段）
- 按 `市场+日期` 合并去重，**字段级互补合并**：逐字段取非空值；冲突时以 Bing API 源为准
- 合并结果同样走 copyright 解析 + 分辨率验证 + schema 校验后落盘
- 更早历史（2009–2021）：本期不做；后续新增 adapter（如 Wayback Machine）即可增量灌入，不破坏已有数据
- **已知风险**：`mkt` 参数会被请求方的网络位置覆盖（实测中国出口网络下所有市场都返回 zh-CN feed）。多市场抓取必须在 GitHub Actions（美国出口）环境验证——首个 workflow 手动触发一次，核对各市场返回的图 ID 含各自市场后缀（如 `_JA-JP`、`_DE-DE`）再纳入每日任务

## 8. 前端（Vue 3 + Vite）

单页应用，三个区块：

1. **筛选栏**：关键词搜索框 + 年份/月份 + 市场 + 国家地区 + 摄影师 + 分辨率；选项来自 `aggregations.json`
2. **瀑布流网格**：缩略图直链 Bing CDN（urlbase + `w=400&h=240` 级参数，零本地存储）；滚动懒加载
3. **详情弹层**：大图预览（分辨率可切换）+ 完整元数据 + 各分辨率下载直链 + 「背后故事」外链（copyrightlink）+ 同图其他市场入口（按 imageKey 关联，数据加载范围内检索）

搜索与数据加载：

- MiniSearch，索引字段：title / desc / location（join 后）/ photographer / region / tags
- **中文单字切分 tokenizer**：「中国雪山」→ 中/国/雪/山 四字符 AND 匹配，命中标题或地点含这些字的记录
- 分片惰性加载：首屏载当年分片 + aggregations.json；筛选到其他年份时增量 fetch 对应 `{market}/{year}.json`
- 页脚声明：图片版权归 Microsoft 及原作者/图库所有，本站仅做元数据索引与链接

## 9. GitHub Actions

- `daily.yml`：`schedule: cron UTC 22:00`（北京时间次日 06:00，确保当日壁纸已发布）+ `workflow_dispatch` 手动触发
  - 步骤：跑 `fetch_daily.py` → 若 `data/` 有 diff 则 commit → 触发 Pages 部署（构建 web 并把 `data/` 复制进产物）
  - 权限按官方 `actions/deploy-pages` 要求的最小集配置
- `backfill.yml`：仅 `workflow_dispatch`，跑回填脚本
- 数据文件就绪即部署，站点无服务端运行时

## 10. 错误处理（仅覆盖真实场景）

| 场景 | 处理 |
|---|---|
| 网络失败 / 接口限流 | 指数退避重试 3 次；仍失败：核心市场让 Actions 红灯并跳过扩展市场，扩展市场只记日志；漏抓靠次日窗口（n=8）自动补 |
| copyright 解析失败 | 不中断；保留 desc，字段置空，日志列出待人工检查 |
| 某市场当天无图 | 跳过，不报错 |
| 分辨率 HEAD 失败 | 该分辨率记 false（图链 404 是真实状态） |

## 11. 测试策略（pytest）

- **copyright 解析器**（价值最高、最易坏的纯函数）：标准格式、无图库、英文句子格式、尾部日期、解析失败等 case
- **imageKey 提取**、**字段级合并逻辑**：纯函数单测
- **JSON schema 校验**：每条记录入库前必过；schema 本身有单测
- **抓取逻辑**：用录制的接口响应 fixture 测解析与合并，本地开发不打真实网络；Actions 中跑真抓取
- 回填与增量共用解析/校验/落盘代码路径，避免两套逻辑漂移

## 12. 明确的 YAGNI 边界

不下载图片本体；无用户系统；无评论收藏；Phase 2 内容搜索仅预留 `tags` 字段；不回填 2021-02/2023-02 之前的历史（留 adapter 口子）；无后端 API（JSON 文件即 API）。
