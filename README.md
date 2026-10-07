# Bing 壁纸图集（bing-wallpaper-atlas）

微软必应每日壁纸的元数据索引站：不只存壁纸，还结构化保存标题、拍摄地、摄影师、图库、日期和可用分辨率，支持按关键词、时间、市场、国家地区、摄影师、分辨率组合搜索。

**图片不做本地存储**，始终直链 Bing CDN。图片版权归 Microsoft 及原作者/图库所有，本站仅做元数据索引与链接。

## 在线访问

**https://imhet.github.io/bing-wallpaper-atlas/**

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
    python -m crawler.fetch_daily       # 手动跑一次增量（扩展市场会先做 mkt 预检，本地网络受限时自动跳过未通过的市场）

    cd web && npm install && npm test   # 前端测试
    npm run dev                         # 本地预览（需先 cp -r data web/dist/data 或配代理）

## 自动更新

GitHub Actions 每日 UTC 22:00（北京时间 06:00）跑增量抓取，数据有变化时提交并部署 Pages。核心市场 zh-cn/en-us 失败会红灯；扩展市场（ja-jp、en-gb、de-de、fr-fr、ko-kr、zh-tw）尽力抓取，可在 `crawler/markets.py` 用 `EXTENDED_ENABLED = False` 关闭。

历史回填在 Actions 里手动触发 `backfill` workflow，或本地 `python -m crawler.backfill`。

## 扩展

- 新回填源：实现 `fetch() -> list[dict]`（字段同 `crawler/sources/niumoo_source.py` 输出），加进 `crawler/backfill.py` 的 `sources` 列表即可
- 内容搜索（Phase 2）：记录已预留 `tags` 字段，图像打标后回填即可被搜索
