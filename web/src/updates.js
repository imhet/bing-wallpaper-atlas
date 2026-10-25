// 更新日志的分组逻辑：按发布日期倒序分组，组内市场按主视角优先序排列。
// 记录里只有壁纸的发布日期（无抓取时间戳），历史数据是当年日期——这是「按发布日浏览」，
// 不是「本站哪天新增了什么」。

import { MARKET_PRIORITY, dedupeByUrlbase } from './api'

export function groupByDate(records, marketPriority = MARKET_PRIORITY) {
  const rank = (m) => {
    const i = marketPriority.indexOf(m)
    return i === -1 ? marketPriority.length : i
  }
  const byDate = new Map()
  for (const r of records) {
    if (!byDate.has(r.date)) byDate.set(r.date, [])
    byDate.get(r.date).push(r)
  }
  return [...byDate.entries()]
    .sort((a, b) => b[0].localeCompare(a[0]))
    // 组内同图跨市场去重（zh-cn 优先代表）：重复画没必要还容易卡
    .map(([date, items]) => ({
      date,
      items: dedupeByUrlbase(items.sort((a, b) => rank(a.market) - rank(b.market) || a.market.localeCompare(b.market))),
    }))
}
