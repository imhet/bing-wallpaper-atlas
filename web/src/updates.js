// 更新日志的分组逻辑：按发布日期倒序分组，组内市场按主视角优先序排列。
// 记录里只有壁纸的发布日期（无抓取时间戳），历史数据是当年日期——这是「按发布日浏览」，
// 不是「本站哪天新增了什么」。

import { MARKET_PRIORITY, dedupeByUrlbase, recordKey } from './api'

export function groupByDate(records, marketPriority = MARKET_PRIORITY) {
  const rank = (m) => {
    const i = marketPriority.indexOf(m)
    return i === -1 ? marketPriority.length : i
  }
  // pass1：图组 → 归属日。同一张图多数市场同天上线，en-us/ja-jp 因时区晚一两天——
  // 那是时区差不是新图，整组归入最早的「本体日」，列表里只出现一次
  const homeDate = new Map()
  for (const r of records) {
    const k = recordKey(r)
    const d = homeDate.get(k)
    if (!d || r.date < d) homeDate.set(k, r.date)
  }
  // pass2：记录归入其图组的归属日
  const byDate = new Map()
  for (const r of records) {
    const d = homeDate.get(recordKey(r))
    if (!byDate.has(d)) byDate.set(d, [])
    byDate.get(d).push(r)
  }
  return [...byDate.entries()]
    .sort((a, b) => b[0].localeCompare(a[0]))
    // 组内同图跨市场去重（zh-cn 优先代表）：重复画没必要还容易卡
    .map(([date, items]) => ({
      date,
      items: dedupeByUrlbase(items.sort((a, b) => rank(a.market) - rank(b.market) || a.market.localeCompare(b.market))),
    }))
}
