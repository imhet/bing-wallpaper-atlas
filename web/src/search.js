import MiniSearch from 'minisearch'

// 中文单字 + 相邻二元组双重切分（拉丁词整体）：'中国雪山' → ['中','中国','国','国雪','雪','雪山','山']。
// 单字负责字面召回，二元组让 AND 匹配到「连续词语」——搜「中国」不再被「国家公园+框景中」这类字符共现误报。
// 假名（ぁ-ヿ）与汉字同等待遇：片假名别名（ヨセミテ等）靠 tags 参与跨语言匹配。
export function tokenize(text) {
  const parts = String(text).toLowerCase().match(/[a-z0-9]+|[ぁ-ヿ一-鿿]/g) || []
  const out = []
  for (let i = 0; i < parts.length; i++) {
    out.push(parts[i])
    if (parts[i].length === 1 && parts[i + 1]?.length === 1) out.push(parts[i] + parts[i + 1])
  }
  return out
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
    const tokens = tokenize(q)
    const andIds = new Set(index.search(q, { combineWith: 'AND' }).map((h) => h.id))
    if (andIds.size > 0) {
      result = result.filter((r) => andIds.has(r.id))
    } else {
      // AND 无命中才回退 OR——优先按词组（二元组/拉丁词）匹配压噪声，无词组（纯单字场景）退回原 token；
      // 注意必须从原始 records 过滤，不能在空结果上继续过滤
      const words = tokens.filter((t) => t.length >= 2)
      const orTokens = words.length > 0 ? words : tokens
      const orIds = new Set(
        index.search(orTokens.join(' '), { combineWith: 'OR', tokenize: () => orTokens }).map((h) => h.id),
      )
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
