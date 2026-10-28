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
    favAt: Date.now(), // 收藏时间：收藏视图按它倒序（最后收藏的排最前）
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

// 导出/导入：localStorage 只存本机，换设备、清浏览器数据就没了——JSON 文件是兜底。
// v1 格式 {app, version, favorites}；同 key 冲突保留 favAt 较新（两台设备各自收藏可互导）
export function exportFavorites(favs) {
  return JSON.stringify({ app: 'bing-wallpaper-atlas', version: 1, favorites: favs }, null, 2)
}

export function importFavorites(existing, jsonString) {
  let doc
  try {
    doc = JSON.parse(jsonString)
  } catch {
    return null
  }
  if (!doc || doc.app !== 'bing-wallpaper-atlas' || doc.version !== 1 || !doc.favorites || typeof doc.favorites !== 'object' || Array.isArray(doc.favorites))
    return null
  const merged = { ...existing }
  let added = 0
  for (const [key, snap] of Object.entries(doc.favorites)) {
    if (!snap || typeof snap !== 'object' || !snap.urlbase) continue // 缺 urlbase 不成其为快照
    if (!merged[key] || (snap.favAt || 0) > (merged[key].favAt || 0)) {
      if (!merged[key]) added += 1
      merged[key] = snap
    }
  }
  return { favorites: merged, added }
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
