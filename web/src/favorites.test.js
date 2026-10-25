import { describe, expect, it } from 'vitest'
import { favoriteKey, loadFavorites, saveFavorites, toggleFavorite } from './favorites'

// 测试用 localStorage 替身：同款接口的内存实现
const memStore = (initial = {}) => {
  const m = new Map(Object.entries(initial))
  return { getItem: (k) => m.get(k) ?? null, setItem: (k, v) => m.set(k, v) }
}

const rec = (over = {}) => ({
  id: 'zh-cn-2026-10-01',
  date: '2026-10-01',
  market: 'zh-cn',
  title: '雪山黄昏',
  desc: '阿尔卑斯山的雪',
  urlbase: '/th?id=OHR.SnowMountain_ZH-CN123',
  location: ['阿尔卑斯'],
  ...over,
})

describe('favoriteKey', () => {
  it('prefers imageKey so cross-market versions share one favorite', () => {
    expect(favoriteKey(rec({ imageKey: 'OHR.SnowMountain' }))).toBe('OHR.SnowMountain')
  })

  it('strips the market suffix from urlbase when imageKey is absent', () => {
    expect(favoriteKey(rec())).toBe('/th?id=OHR.SnowMountain')
  })
})

describe('toggleFavorite', () => {
  it('adds a snapshot with safe shapes for missing fields', () => {
    const favs = toggleFavorite({}, rec({ title: '', location: undefined, tags: undefined }))
    const snap = favs['/th?id=OHR.SnowMountain']
    expect(snap.date).toBe('2026-10-01')
    expect(snap.title).toBe('')
    expect(snap.location).toEqual([])
    expect(snap.tags).toEqual([])
    expect(snap.resolutions).toEqual({})
  })

  it('removes the entry on a second toggle', () => {
    const favs = toggleFavorite({}, rec())
    expect(Object.keys(toggleFavorite(favs, rec()))).toHaveLength(0)
  })

  it('toggling another market of the same image removes the existing favorite', () => {
    const favs = toggleFavorite({}, rec())
    const jp = rec({ id: 'ja-jp-2026-10-01', market: 'ja-jp', urlbase: '/th?id=OHR.SnowMountain_JA-JP456' })
    expect(toggleFavorite(favs, jp)).toEqual({})
  })
})

describe('loadFavorites / saveFavorites', () => {
  it('returns an empty object when nothing is stored', () => {
    expect(loadFavorites(memStore())).toEqual({})
  })

  it('degrades to an empty object on corrupt or non-object JSON', () => {
    expect(loadFavorites(memStore({ favorites: '{oops' }))).toEqual({})
    expect(loadFavorites(memStore({ favorites: '[1,2]' }))).toEqual({})
  })

  it('round-trips through saveFavorites', () => {
    const store = memStore()
    const favs = toggleFavorite({}, rec())
    saveFavorites(store, favs)
    expect(loadFavorites(store)).toEqual(favs)
  })
})
