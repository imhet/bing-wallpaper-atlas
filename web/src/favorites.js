// 本地收藏：localStorage 持久化，按图组归一键存（同图跨市场算同一张，切市场版本不丢）。
// 存的是记录快照而非 id 列表——全量 records 加载完成前收藏视图也能渲染，详情弹层
// 依赖的字段（location/tags/…）在快照里保证安全形状。

import { imgKey } from './api'

const STORAGE_KEY = 'favorites'

export const favoriteKey = (r) => r.imageKey || imgKey(r.urlbase)

function snapshot(r) {
  return {
    id: r.id,
    date: r.date,
    market: r.market,
    urlbase: r.urlbase,
    imageKey: r.imageKey,
    title: r.title || '',
    desc: r.desc || '',
    location: r.location || [],
    region: r.region || '',
    photographer: r.photographer || '',
    gallery: r.gallery || '',
    copyrightlink: r.copyrightlink || '',
    tags: r.tags || [],
    content_tags: r.content_tags || [],
    resolutions: r.resolutions || {},
  }
}

export function toggleFavorite(favs, record) {
  const key = favoriteKey(record)
  if (favs[key]) {
    const rest = { ...favs }
    delete rest[key]
    return rest
  }
  return { ...favs, [key]: snapshot(record) }
}

export function loadFavorites(store) {
  try {
    const raw = store.getItem(STORAGE_KEY)
    if (!raw) return {}
    const obj = JSON.parse(raw)
    return obj && typeof obj === 'object' && !Array.isArray(obj) ? obj : {}
  } catch {
    return {} // 手工改坏/旧版本残留：收藏清空好过整站报错
  }
}

export function saveFavorites(store, favs) {
  store.setItem(STORAGE_KEY, JSON.stringify(favs))
}
