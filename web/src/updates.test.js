import { describe, expect, it } from 'vitest'
import { groupByDate } from './updates'

const rec = (date, market) => ({ id: `${market}-${date}`, date, market, urlbase: `/th?id=OHR.X_${market}1` })

// 大写市场后缀符合 imgKey 的剥离正则（同真实数据 OHR.Name_ZH-CN123）：同 urlbase 归一 = 同一张图
const sameImg = (date, market) => ({
  id: `${market}-${date}`,
  date,
  market,
  urlbase: `/th?id=OHR.X_${market.toUpperCase()}1`,
})

describe('groupByDate', () => {
  it('groups records by date in descending order', () => {
    // 注意用不同的图：同 urlbase 跨天会被同图去重合并（见下方用例），不构成两个日期组
    const groups = groupByDate([
      rec('2026-10-01', 'zh-cn'),
      { ...rec('2026-10-03', 'en-us'), urlbase: '/th?id=OHR.Y_EN-US1' },
      rec('2026-10-01', 'en-us'),
    ])
    expect(groups.map((g) => g.date)).toEqual(['2026-10-03', '2026-10-01'])
  })

  it('orders markets within a day by priority (zh-cn first)', () => {
    const groups = groupByDate([
      rec('2026-10-01', 'fr-fr'),
      rec('2026-10-01', 'zh-cn'),
      rec('2026-10-01', 'en-us'),
    ])
    expect(groups[0].items.map((r) => r.market)).toEqual(['zh-cn', 'en-us', 'fr-fr'])
  })

  it('returns an empty array for no records', () => {
    expect(groupByDate([])).toEqual([])
  })

  it('dedupes same-image cross-market records within a day (zh-cn as the rep)', () => {
    // 同天同图多市场只画一张（zh-cn 优先代表），避免重复渲染卡顿
    const groups = groupByDate([sameImg('2026-10-01', 'en-us'), sameImg('2026-10-01', 'zh-cn'), sameImg('2026-10-01', 'fr-fr')])
    expect(groups[0].items).toHaveLength(1)
    expect(groups[0].items[0].market).toBe('zh-cn')
  })

  it('keeps different images of the same day apart', () => {
    const groups = groupByDate([rec('2026-10-01', 'zh-cn'), rec('2026-10-01', 'en-us')])
    expect(groups[0].items).toHaveLength(2)
  })

  it('dedupes same-image cross-day records into the earliest day (timezone offset)', () => {
    // en-us 比多数市场晚一天（时区差不是新图）：同图只保留本体日（最早日期），代表 zh-cn
    const groups = groupByDate([
      sameImg('2026-10-23', 'en-us'),
      sameImg('2026-10-22', 'zh-cn'),
      sameImg('2026-10-22', 'fr-fr'),
      rec('2026-10-23', 'ja-jp'), // 另一张图：10-23 组不至于变空
    ])
    const g22 = groups.find((g) => g.date === '2026-10-22')
    const g23 = groups.find((g) => g.date === '2026-10-23')
    expect(g22.items).toHaveLength(1)
    expect(g22.items[0].market).toBe('zh-cn')
    expect(g23.items.map((r) => r.market)).toEqual(['ja-jp'])
  })
})
