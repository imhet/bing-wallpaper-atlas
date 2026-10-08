# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目定位

Bing 每日壁纸的元数据索引站（仅索引元数据，**图片永不落地**，直链 Bing CDN）。Python 抓取 + 分片 JSON 数据 + Vue 3 静态站，GitHub Actions 每日自动抓取并部署到 Pages：https://imhet.github.io/bing-wallpaper-atlas/

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
# 注意：vite build 会清空 dist/，dist/data 必须每次重新拷贝，否则预览站无数据

# 每日增量 / 历史回填
./.venv/bin/python -m crawler.fetch_daily --data-dir data
./.venv/bin/python -m crawler.backfill --data-dir data [--markets zh-cn] [--skip-resolution-check]
```

本机直连 github.com 主站常超时（api.github.com 可直连）：`git push`、device 授权等操作挂 `HTTPS_PROXY=http://127.0.0.1:1087`。

## 架构

### 数据流水线（crawler/）

```
sources/niumoo_source.py      历史源：niumoo 仓库 images.json（多年全历史）
sources/bing_api_source.py    增量源：HPImageArchive.aspx 近 8 天 × 8 市场
        ↓
backfill.py / fetch_daily.py  build_record() 拼 15 字段记录：
                              copyright_parser 解析 ©（永不抛异常）
                              regions.py 做国家归一（COUNTRY_ALIASES + 否定短语）
                              geo_enrich 写入多语言地名 tags（跨语言搜索的桥）
        ↓
merge.py                      merge_records()：源优先级非空覆盖；(market,date) 冲突抛错
        ↓
storage.py                    data/{market}/{year}.json 分片 + aggregations.json
        ↓
.github/workflows/            daily.yml（cron UTC 22:00）与 backfill.yml 共用
                              concurrency 组 bing-wallpaper-deploy，抓取→提交→构建→部署 Pages
```

纯前端改动上线用 `gh workflow run daily.yml -f force_deploy=true`（数据无变化时也能部署）。

### 前端（web/）

Vue 3 + MiniSearch，无路由无状态库。`api.js` 用相对路径 `./data/...` 惰性按年加载分片（App.vue 的 `watch(filters.year)` 驱动）。`vite.config.js` 设 `base: './'` 以兼容 Pages 子路径。

**搜索（search.js）是本项目最精巧的部分，改动前先读懂**：`tokenize()` 把中文切成「单字 + 相邻二元组」（`中国雪山` → `中/中国/国/国雪/雪/雪山/山`）——单字负责字面召回，二元组让 AND 匹配到连续词语，否则搜「中国」会被「国家公园…框景中」这类字符共现误报。AND 无命中时回退到**词组级** OR（用查询选项 `tokenize: () => orTokens` 覆盖，防止 join 后被重切成单字）。

## 领域规则（不读代码会踩的坑）

- **mkt 预检（verify_mkt）**：Bing 按网络位置覆盖 `mkt` 参数的 feed。任何环境跑回填前必须预检，不过的市场必须剔除——ko-kr、zh-tw 连美国出口都被路由污染（线上无此两市场数据是预期行为），扩展市场靠 urlbase 里的 `_JA-JP123` 后缀正则验证
- **niumoo 源的 date 系统性 +1 天**：必须减一归一化再入库（`_shift_date`），(market,date) 去重、未来日期丢弃
- **记录 schema**（schema.py）：15 字段 `additionalProperties: false`，id 形如 `zh-cn-2023-10-05`
- **aggregations.json 无时间戳**：数据不变时重新生成应产生零 git diff，别引入易变字段
- **分辨率探测**（resolutions.py）：uhd/fhd/hd/thumb 四档 HEAD 探测是回填最耗时的一段（interval 0.2s）；已带 resolutions 的记录 skip-guard 会跳过
- 前端详情弹层的分辨率按钮按 `RES_SUFFIX` 白名单生成，thumb 只做网格缩略图，不进弹层
- **多语言地名词典**（geo_enrich.py + geo_aliases.json，302 组）：文本命中任一写法即把「规范中文名 + 全组别名」写入 tags，实现跨语言搜索（优胜美地=yosemite=ヨセミテ）。长尾地名搜不到时：词典加条目 → `python -m crawler.geo_enrich --data-dir data` 重跑，**搜索端零改动**；拉丁别名 `\b` 词边界防误报（comparison 不中 paris）

## 测试约定

后端 pytest（tests/ 与 crawler/ 镜像分文件，`conftest.py` 的 `make_record` fixture 供 15 字段合法记录）；前端 vitest（`search.test.js` 的三条 mock 记录专为搜索误报场景设计——拱门国家公园记录用于验证「中国」不再误报）。改搜索逻辑必须先跑 `npm run test --prefix web`。
