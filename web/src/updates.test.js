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
    const groups = groupByDate([rec('2026-10-01', 'zh-cn'), rec('2026-10-03', 'en-us'), rec('2026-10-01', 'en-us')])
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
})
