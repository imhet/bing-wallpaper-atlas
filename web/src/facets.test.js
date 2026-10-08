import { describe, expect, it } from 'vitest'
import { buildIndex } from './search'
import { computeFacets } from './facets'

const records = [
  { id: 'zh-2023-a', market: 'zh-cn', date: '2023-01-05', title: '云海', desc: '',
    location: [], region: '中国', photographer: 'Li', gallery: null, tags: [],
    resolutions: { uhd: true, thumb: true } },
  { id: 'zh-2024-b', market: 'zh-cn', date: '2024-02-01', title: '雪山', desc: '',
    location: [], region: '', photographer: '', gallery: null, tags: [],
    resolutions: { uhd: false, fhd: true, thumb: true } },
  { id: 'us-2024-c', market: 'en-us', date: '2024-02-10', title: 'Alps', desc: '',
    location: [], region: '美国', photographer: 'Doe', gallery: null, tags: [],
    resolutions: { uhd: true, fhd: true, thumb: true } },
  { id: 'us-2025-d', market: 'en-us', date: '2025-03-15', title: 'Fjord', desc: '',
    location: [], region: '美国', photographer: '', gallery: null, tags: [],
    resolutions: { hd: true, thumb: true } },
]

const index = buildIndex(records)
const facetsOf = (filters) => computeFacets(index, records, '', filters)

describe('computeFacets', () => {
  it('year counts follow the market filter (sum equals that market total)', () => {
    // 涛总的核心诉求：选 zh-cn 后年份计数是 zh-cn 内部分布，加起来正好是 zh-cn 总数
    expect(facetsOf({ market: 'zh-cn' }).year).toEqual([
      { name: '2023', count: 1 },
      { name: '2024', count: 1 },
    ])
  })

  it('market counts follow the year filter', () => {
    expect(facetsOf({ year: 2024 }).market).toEqual([
      { name: 'en-us', count: 1 },
      { name: 'zh-cn', count: 1 },
    ])
  })

  it('month counts follow other filters and names drop the leading zero', () => {
    expect(facetsOf({}).month).toEqual([
      { name: '1', count: 1 },
      { name: '2', count: 2 },
      { name: '3', count: 1 },
    ])
    expect(facetsOf({ market: 'en-us' }).month).toEqual([
      { name: '2', count: 1 },
      { name: '3', count: 1 },
    ])
  })

  it('resolution counts each usable tier once and never lists thumb', () => {
    expect(facetsOf({}).resolution).toEqual([
      { name: 'uhd', count: 2 },
      { name: 'fhd', count: 2 },
      { name: 'hd', count: 1 },
    ])
  })

  it('keeps the selected value with count 0 when filtered out', () => {
    // zh-cn 在 2025 无记录：market 下拉仍要显示当前选中值，否则 select 显示错位
    expect(facetsOf({ market: 'zh-cn', year: 2025 }).market).toEqual([
      { name: 'en-us', count: 1 },
      { name: 'zh-cn', count: 0 },
    ])
  })

  it('counts respect the search query as well', () => {
    expect(computeFacets(index, records, '雪山', {}).market).toEqual([{ name: 'zh-cn', count: 1 }])
  })

  it('omits empty region/photographer values from options', () => {
    expect(facetsOf({}).region.map((r) => r.name)).toEqual(['美国', '中国'])
    // 计数降序、同计数字母序：Li 与 Doe 各 1 张，Doe 在前
    expect(facetsOf({}).photographer.map((p) => p.name)).toEqual(['Doe', 'Li'])
  })
})
