import { describe, expect, it } from 'vitest'
import { decodeFilters, encodeFilters } from './urlState'

describe('urlState', () => {
  it('roundtrips all fields', () => {
    const f = { query: '阿尔卑斯', market: 'zh-cn', year: 2023, month: 10, region: '瑞士', photographer: 'Li Hua', resolution: 'uhd' }
    expect(decodeFilters(encodeFilters(f))).toEqual(f)
  })

  it('omits empty values from the query string', () => {
    const s = encodeFilters({ query: '', market: '', year: '', month: '', region: '', photographer: '', resolution: 'uhd' })
    expect(s).toBe('?resolution=uhd')
  })

  it('returns empty string for an all-empty filter set', () => {
    expect(encodeFilters({ query: '', year: '' })).toBe('')
  })

  it('decodes numbers and falls back on garbage', () => {
    expect(decodeFilters('?year=2023&q=雪山').year).toBe(2023)
    expect(decodeFilters('?year=abc').year).toBe('')
    expect(decodeFilters('')).toEqual({ query: '', market: '', year: '', month: '', region: '', photographer: '', resolution: '' })
  })
})
