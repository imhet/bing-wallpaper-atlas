import { describe, expect, it, vi } from 'vitest'
import { loadYearShards } from './api'

describe('loadYearShards', () => {
  it('fetches every market that has the year and flattens', async () => {
    const calls = []
    vi.stubGlobal('fetch', (url) => {
      calls.push(url)
      return Promise.resolve({ ok: true, json: () => Promise.resolve([{ id: url }]) })
    })
    const agg = { years_by_market: { 'zh-cn': [2023, 2024], 'en-us': [2024] } }
    const out = await loadYearShards(agg, 2024)
    expect(calls).toEqual(['./data/zh-cn/2024.json', './data/en-us/2024.json'])
    expect(out).toHaveLength(2)
    vi.unstubAllGlobals()
  })

  it('fetches nothing for a year no market has', async () => {
    const calls = []
    vi.stubGlobal('fetch', (url) => {
      calls.push(url)
      return Promise.resolve({ ok: true, json: () => Promise.resolve([]) })
    })
    const out = await loadYearShards({ years_by_market: { 'zh-cn': [2023] } }, 2099)
    expect(calls).toEqual([])
    expect(out).toEqual([])
    vi.unstubAllGlobals()
  })
})
