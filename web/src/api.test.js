import { describe, expect, it, vi } from 'vitest'
import { dedupeByUrlbase, fetchJSON, imageUrl, loadAllRecords, loadYearShards, mapsUrl, resetCdnProbe, thumbUrl } from './api'

describe('fetchJSON 的 jsDelivr 分流（国内直连 github.io 只有几十 KB/s）', () => {
  const CDN = 'https://cdn.jsdelivr.net/gh/imhet/bing-wallpaper-atlas@main/data/zh-cn/2026.json'

  it('HEAD 预检可达时数据请求走 jsDelivr', async () => {
    resetCdnProbe()
    const calls = []
    vi.stubGlobal('fetch', (url, init) => {
      calls.push([url, init?.method || 'GET'])
      if (init?.method === 'HEAD') return Promise.resolve({ ok: true })
      return Promise.resolve({ ok: true, json: () => Promise.resolve([{ id: 'via-cdn' }]) })
    })
    const out = await fetchJSON('./data/zh-cn/2026.json')
    expect(calls[0]).toEqual(['https://cdn.jsdelivr.net/gh/imhet/bing-wallpaper-atlas@main/data/aggregations.json', 'HEAD'])
    expect(calls[1]).toEqual([CDN, 'GET'])
    expect(out).toEqual([{ id: 'via-cdn' }])
    vi.unstubAllGlobals()
  })

  it('HEAD 预检失败走 Pages 相对路径', async () => {
    resetCdnProbe()
    const calls = []
    vi.stubGlobal('fetch', (url) => {
      calls.push(url)
      if (url.includes('jsdelivr')) return Promise.reject(new Error('unreachable'))
      return Promise.resolve({ ok: true, json: () => Promise.resolve([{ id: 'local' }]) })
    })
    expect(await fetchJSON('./data/zh-cn/2026.json')).toEqual([{ id: 'local' }])
    expect(calls).toEqual([expect.stringContaining('jsdelivr'), './data/zh-cn/2026.json'])
    vi.unstubAllGlobals()
  })

  it('CDN 拉取中途失败降级 Pages，且后续请求不再反复探测', async () => {
    resetCdnProbe()
    const calls = []
    vi.stubGlobal('fetch', (url, init) => {
      calls.push([url, init?.method || 'GET'])
      if (calls.length === 1) return Promise.resolve({ ok: true }) // HEAD 可达
      if (calls.length === 2) return Promise.reject(new Error('cdn json failed'))
      return Promise.resolve({ ok: true, json: () => Promise.resolve([{ id: 'local' }]) })
    })
    expect(await fetchJSON('./data/zh-cn/2026.json')).toEqual([{ id: 'local' }])
    const n = calls.length
    expect(await fetchJSON('./data/zh-cn/2025.json')).toEqual([{ id: 'local' }])
    expect(calls.length).toBe(n + 1) // 第二次调用只有一个请求：直接走本地
    expect(calls[n][0]).toBe('./data/zh-cn/2025.json')
    vi.unstubAllGlobals()
  })

  it('非 data 路径不探测 jsDelivr（站点自身资源没有分流需求）', async () => {
    resetCdnProbe()
    const calls = []
    vi.stubGlobal('fetch', (url, init) => {
      calls.push([url, init?.method || 'GET'])
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    await fetchJSON('./other.json')
    expect(calls).toEqual([['./other.json', 'GET']])
    vi.unstubAllGlobals()
  })
})

describe('mapsUrl（详情页地点跳地图）', () => {
  it('joins location parts and encodes them into a Google Maps search URL', () => {
    expect(mapsUrl(['张家界国家森林公园', '湖南'])).toBe(
      `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent('张家界国家森林公园 湖南')}`,
    )
  })

  it('keeps working for empty or missing location', () => {
    expect(mapsUrl([])).toBe(`https://www.google.com/maps/search/?api=1&query=`)
    expect(mapsUrl(undefined)).toBe(`https://www.google.com/maps/search/?api=1&query=`)
  })
})

describe('loadYearShards', () => {
  it('fetches every market that has the year and flattens', async () => {
    const calls = []
    vi.stubGlobal('fetch', (url) => {
      if (String(url).includes('jsdelivr')) return Promise.resolve({ ok: false }) // CDN 不可达：走 Pages 路径
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
      if (String(url).includes('jsdelivr')) return Promise.resolve({ ok: false })
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
      String(url).includes('jsdelivr')
        ? Promise.resolve({ ok: false })
        : Promise.resolve({
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
      if (String(url).includes('jsdelivr')) return Promise.resolve({ ok: false })
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
      String(url).includes('jsdelivr')
        ? Promise.resolve({ ok: false })
        : Promise.resolve({
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

  it('同一 imageKey 的镜像记录跨市场折叠为一张（镜像 urlbase 各市场路径不同）', () => {
    const recs = [
      { id: 'de', market: 'de-de', date: '2024-04-02', imageKey: 'JutlandSpring', urlbase: 'https://bing.npanuhin.me/DE/de/2024-04-02.jpg' },
      { id: 'fr', market: 'fr-fr', date: '2024-04-02', imageKey: 'JutlandSpring', urlbase: 'https://bing.npanuhin.me/FR/fr/2024-04-02.jpg' },
      { id: 'us', market: 'en-us', date: '2024-04-02', imageKey: 'JutlandSpring', urlbase: '/th?id=OHR.JutlandSpring_EN-US123' },
      { id: 'cn', market: 'zh-cn', date: '2024-04-02', imageKey: 'KyrgyzstanRainbow', urlbase: '/th?id=OHR.KyrgyzstanRainbow_ZH-CN1' },
    ]
    expect(dedupeByUrlbase(recs).map((r) => r.id)).toEqual(['us', 'cn'])
  })

  it('无 imageKey 的镜像深史记录保持独立（不同日期不误合并）', () => {
    const recs = [
      { id: 'a', market: 'en-us', date: '2011-06-01', imageKey: null, urlbase: 'https://bing.npanuhin.me/US/en/2011-06-01.jpg' },
      { id: 'b', market: 'en-us', date: '2011-06-02', imageKey: null, urlbase: 'https://bing.npanuhin.me/US/en/2011-06-02.jpg' },
    ]
    expect(dedupeByUrlbase(recs).map((r) => r.id)).toEqual(['a', 'b'])
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
