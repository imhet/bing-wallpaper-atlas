import { describe, expect, it } from 'vitest'
import { groupByDate } from './updates'

const rec = (date, market) => ({ id: `${market}-${date}`, date, market, urlbase: `/th?id=OHR.X_${market}1` })

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
})
