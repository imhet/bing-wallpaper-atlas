import { describe, expect, it, vi } from 'vitest'
import { loadAllRecords, loadYearShards } from './api'

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

  it('loadAllRecords sorts newest first (search/首屏默认全部年份时最新壁纸在前)', async () => {
    // 分片按 market 字母序 concat：2024 记录在前也必须重排为 date 倒序
    vi.stubGlobal('fetch', (url) =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve(
            url.includes('2026')
              ? [{ id: 'zh-2026', date: '2026-01-01' }]
              : url.includes('2025')
                ? [{ id: 'zh-2025', date: '2025-06-01' }]
                : [{ id: 'us-2024', date: '2024-12-31' }],
          ),
      }),
    )
    const out = await loadAllRecords({ years_by_market: { 'en-us': [2024], 'zh-cn': [2025, 2026] } })
    expect(out.map((r) => r.id)).toEqual(['zh-2026', 'zh-2025', 'us-2024'])
    vi.unstubAllGlobals()
  })
})
