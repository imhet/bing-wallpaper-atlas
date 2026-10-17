import { describe, expect, it, vi } from 'vitest'
import { dedupeByUrlbase, imageUrl, loadAllRecords, loadYearShards, thumbUrl } from './api'

describe('loadYearShards', () => {
  it('fetches every market that has the year and flattens', async () => {
    const calls = []
    vi.stubGlobal('fetch', (url) => {
      calls.push(url)
      return Promise.resolve({ ok: true, json: () => Promise.resolve([{ id: url, date: '2024-01-01' }]) })
    })
    const agg = { years_by_market: { 'zh-cn': [2023, 2024], 'en-us': [2024] } }
    const out = await loadYearShards(agg, 2024)
    expect(calls).toEqual(['./data/zh-cn/2024.json', './data/en-us/2024.json'])
    expect(out).toHaveLength(2)
    vi.unstubAllGlobals()
  })

  it('markets 参数只拉指定市场（首屏分级：主视角市场先出图，其余后台补）', async () => {
    const calls = []
    vi.stubGlobal('fetch', (url) => {
      calls.push(url)
      return Promise.resolve({ ok: true, json: () => Promise.resolve([{ id: url, date: '2026-01-01' }]) })
    })
    const agg = { years_by_market: { 'zh-cn': [2026], 'en-us': [2026], 'de-de': [2026], 'ja-jp': [2026] } }
    const out = await loadYearShards(agg, 2026, ['zh-cn', 'en-us'])
    expect(calls).toEqual(['./data/zh-cn/2026.json', './data/en-us/2026.json'])
    expect(out).toHaveLength(2)
    vi.unstubAllGlobals()
  })

  it('returns records newest first（首屏一级直接渲染，分片文件是日期正序，不排序会先显示 1 月）', async () => {
    vi.stubGlobal('fetch', (url) =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve(
            url.includes('zh-cn')
              ? [{ id: 'zh-01', date: '2026-01-01' }, { id: 'zh-10', date: '2026-10-14' }]
              : [{ id: 'us-06', date: '2026-06-01' }],
          ),
      }),
    )
    const out = await loadYearShards({ years_by_market: { 'zh-cn': [2026], 'en-us': [2026] } }, 2026)
    expect(out.map((r) => r.date)).toEqual(['2026-10-14', '2026-06-01', '2026-01-01'])
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

describe('dedupeByUrlbase', () => {
  it('same image across markets keeps one record, zh-cn preferred, order preserved', () => {
    // Bing 同一天全球同图：urlbase 仅市场后缀不同，归一后只留代表记录
    const recs = [
      { id: 'us', market: 'en-us', date: '2026-10-08', urlbase: '/th?id=OHR.Fuji_EN-US123' },
      { id: 'jp', market: 'ja-jp', date: '2026-10-08', urlbase: '/th?id=OHR.Fuji_JA-JP789' },
      { id: 'zh', market: 'zh-cn', date: '2026-10-08', urlbase: '/th?id=OHR.Fuji_ZH-CN456' },
      { id: 'other', market: 'en-us', date: '2026-10-07', urlbase: '/th?id=OHR.Alps_EN-US111' },
    ]
    expect(dedupeByUrlbase(recs).map((r) => r.id)).toEqual(['zh', 'other'])
  })

  it('falls back to alphabetical market when no priority market in group', () => {
    const recs = [
      { id: 'jp', market: 'ja-jp', date: '2026-10-08', urlbase: '/th?id=OHR.Fuji_JA-JP789' },
      { id: 'fr', market: 'fr-fr', date: '2026-10-08', urlbase: '/th?id=OHR.Fuji_FR-FR001' },
    ]
    expect(dedupeByUrlbase(recs).map((r) => r.id)).toEqual(['fr'])
  })

  it('mirror absolute urlbase（npanuhin 深史）stays a standalone group', () => {
    const recs = [{ id: 'us', market: 'en-us', date: '2011-06-01', urlbase: 'https://bing.npanuhin.me/US/en/2011-06-01.jpg' }]
    expect(dedupeByUrlbase(recs).map((r) => r.id)).toEqual(['us'])
  })
})

describe('imageUrl / thumbUrl 对镜像绝对 URL（npanuhin 深史源）', () => {
  it('absolute urlbase returns as-is regardless of suffix', () => {
    const u = 'https://bing.npanuhin.me/US/en/2011-06-01.jpg'
    expect(imageUrl(u, '_UHD.jpg')).toBe(u)
  })

  it('thumbUrl 对镜像记录返回本地预生成 webp（gen_thumbs 产物，按 market/年/日期）', () => {
    // 镜像原图 74~339KB 且无边缘缓存，网格直接加载太慢；缩略图走本地 webp
    expect(
      thumbUrl({ urlbase: 'https://bing.npanuhin.me/US/en/2011-06-01.jpg', market: 'en-us', date: '2011-06-01' }),
    ).toBe('./data/thumbs/en-us/2011/2011-06-01.webp')
  })

  it('bing relative urlbase keeps CDN composition', () => {
    expect(imageUrl('/th?id=OHR.X_ZH-CN1', '_400x240.jpg')).toBe('https://www.bing.com/th?id=OHR.X_ZH-CN1_400x240.jpg')
    expect(thumbUrl({ urlbase: '/th?id=OHR.X_ZH-CN1', resolutions: { thumb: true } }))
      .toBe('https://www.bing.com/th?id=OHR.X_ZH-CN1_400x240.jpg')
  })
})
