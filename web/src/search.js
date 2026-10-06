import MiniSearch from 'minisearch'

// 中文单字切分 + 拉丁词整体，'中国雪山' → ['中','国','雪','山']
export function tokenize(text) {
  return (String(text).toLowerCase().match(/[a-z0-9]+|[一-鿿]/g) || [])
}

const FIELDS = ['title', 'desc', 'location', 'region', 'photographer', 'gallery', 'tags']

export function buildIndex(records) {
  const docs = records.map((r) => ({ ...r, location: (r.location || []).join(' ') }))
  const index = new MiniSearch({ fields: FIELDS, storeFields: ['id'], tokenize })
  index.addAll(docs)
  return index
}

export function searchRecords(index, records, query, filters) {
  let result = records
  const q = (query || '').trim()
  if (q) {
    const andIds = new Set(index.search(q, { combineWith: 'AND' }).map((h) => h.id))
    if (andIds.size > 0) {
      result = result.filter((r) => andIds.has(r.id))
    } else {
      // AND 无命中才回退 OR——注意必须从原始 records 过滤，不能在空结果上继续过滤
      const orIds = new Set(index.search(q, { combineWith: 'OR' }).map((h) => h.id))
      result = result.filter((r) => orIds.has(r.id))
    }
  }
  return result.filter(
    (r) =>
      (!filters.market || r.market === filters.market) &&
      (!filters.year || r.date.slice(0, 4) === String(filters.year)) &&
      (!filters.month || r.date.slice(5, 7) === String(filters.month).padStart(2, '0')) &&
      (!filters.region || r.region === filters.region) &&
      (!filters.photographer || r.photographer === filters.photographer) &&
      (!filters.resolution || r.resolutions?.[filters.resolution] === true),
  )
}
