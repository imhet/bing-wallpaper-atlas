import MiniSearch from 'minisearch'
import { suggestFromDict } from './suggest'

// 中文单字 + 相邻二元组双重切分（拉丁词整体）：'中国雪山' → ['中','中国','国','国雪','雪','雪山','山']。
// 单字负责字面召回，二元组让 AND 匹配到「连续词语」——搜「中国」不再被「国家公园+框景中」这类字符共现误报。
// 假名（ぁ-ヿ）与汉字同等待遇：片假名别名（ヨセミテ等）靠 tags 参与跨语言匹配。
export function tokenize(text) {
  const src = String(text).toLowerCase()
  const parts = [...src.matchAll(/[a-z0-9]+|[ぁ-ヿ一-鿿]/g)]
  const out = []
  for (let i = 0; i < parts.length; i++) {
    out.push(parts[i][0])
    // 二元组必须原文相邻：标点/空格分隔的两字不组词（「湖，南」≠「湖南」，否则跨标点假词污染召回）
    if (
      parts[i][0].length === 1 &&
      parts[i + 1]?.[0].length === 1 &&
      parts[i + 1].index - parts[i].index === 1
    )
      out.push(parts[i][0] + parts[i + 1][0])
  }
  return out
}

const FIELDS = ['title', 'desc', 'location', 'region', 'photographer', 'gallery', 'tags', 'content_tags']

export function buildIndex(records) {
  const docs = records.map((r) => ({ ...r, location: (r.location || []).join(' ') }))
  const index = new MiniSearch({ fields: FIELDS, storeFields: ['id'], tokenize })
  index.addAll(docs)
  return index
}

// 命中高亮分段：原始查询串 + 词组级 token + 词典桥接别名（京都→kyoto）按长度优先，
// 在文本中标出命中区间。返回 [{text, hit}] 供模板渲染 <mark>，不用 v-html 以规避 XSS。
export function highlightParts(text, query, aliasData = null) {
  const src = String(text || '')
  const raw = String(query || '').trim()
  const bridged = aliasData ? suggestFromDict(raw, aliasData) : []
  const tokens = [...new Set([raw, ...bridged, ...tokenize(raw).filter((t) => t.length >= 2)])]
    .filter((t) => t.length >= 2)
    .sort((a, b) => b.length - a.length)
  if (!tokens.length) return [{ text: src, hit: false }]
  const re = new RegExp(
    tokens.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|'),
    'gi',
  )
  const parts = []
  let last = 0
  for (const m of src.matchAll(re)) {
    if (m.index > last) parts.push({ text: src.slice(last, m.index), hit: false })
    parts.push({ text: m[0], hit: true })
    last = m.index + m[0].length
  }
  if (last < src.length) parts.push({ text: src.slice(last), hit: false })
  return parts
}

// 纯日期查询 → 记录谓词；非日期返回 null 走全文检索。
// 20261001 / 2026-10-01 → 精确当天；10-01 / 1001 → 每一年的 MM-DD；
// 四位非日期（2026）→ 年份。月 1-12 日 1-31 宽松校验，越界即不当日期处理。
export function parseDateQuery(q) {
  const s = String(q).trim().replace(/[-./]/g, '')
  if (/^\d{8}$/.test(s)) {
    const y = s.slice(0, 4), m = +s.slice(4, 6), d = +s.slice(6, 8)
    if (m >= 1 && m <= 12 && d >= 1 && d <= 31) return (r) => r.date === `${y}-${s.slice(4, 6)}-${s.slice(6, 8)}`
  } else if (/^\d{4}$/.test(s)) {
    const m = +s.slice(0, 2), d = +s.slice(2, 4)
    if (m >= 1 && m <= 12 && d >= 1 && d <= 31) return (r) => r.date.slice(5) === s.slice(0, 2) + '-' + s.slice(2, 4)
    return (r) => r.date.slice(0, 4) === s
  }
  return null
}

// 单段搜索：AND 优先，无命中才回退词组级 OR（纯单字场景退回原 token）。
// 必须独立成段调用——跨词二元组（「藏的/的雪」）会让整串 AND 永远落空。
// 返回 id → 相关度分数：集合过滤之后要用它把最相关的结果排到前面。
function segmentScores(index, seg) {
  const andHits = index.search(seg, { combineWith: 'AND' })
  if (andHits.length) return new Map(andHits.map((h) => [h.id, h.score]))
  const tokens = tokenize(seg)
  const words = tokens.filter((t) => t.length >= 2)
  const orTokens = words.length > 0 ? words : tokens
  return new Map(
    index.search(orTokens.join(' '), { combineWith: 'OR', tokenize: () => orTokens })
      .map((h) => [h.id, h.score]),
  )
}

// 分面筛选独立成函数：语义融合需要「已过滤的候选集」做同口径重排，
// 否则语义会把年份/市场筛选掉的图带回结果列表。
export function applyFilters(records, filters) {
  return records.filter(
    (r) =>
      (!filters.market || r.market === filters.market) &&
      (!filters.year || r.date.slice(0, 4) === String(filters.year)) &&
      (!filters.month || r.date.slice(5, 7) === String(filters.month).padStart(2, '0')) &&
      (!filters.region || r.region === filters.region) &&
      (!filters.photographer || r.photographer === filters.photographer) &&
      (!filters.resolution || r.resolutions?.[filters.resolution] === true),
  )
}

// 查询里的地理限定段：切段后完整等于某条记录 region 值的段（「中国的秋景」→ ['中国']）。
// 语义层（CLIP 概念）不懂国别，语义候选需要用它做地理约束——见 semantic.js geoFilterSemScores。
export function extractGeoTerms(query, regions) {
  const set = new Set(regions)
  return (query || '').trim().split(/[\s,，、;；!！?？的]+/).filter((seg) => set.has(seg))
}

// 关键词层缓存（单槽）：打分是大头（tokenize + MiniSearch 段间 AND），筛选是廉价的谓词过滤。
// 分面计数对同一 query 用 6 组不同筛选重查（facets.js computeFacets），不缓存就重复打分 6 次。
// index/records 引用参与比较——分级加载/全量补齐整体替换 records 后自然失效
let kwCache = { index: null, records: null, query: null, result: null }

export function keywordStage(index, records, query) {
  const q = (query || '').trim()
  if (kwCache.index === index && kwCache.records === records && kwCache.query === q) return kwCache.result
  let result = records
  if (q) {
    const dateMatch = parseDateQuery(q)
    if (dateMatch) {
      result = result.filter(dateMatch)
    } else {
      // 多关键词：空格/标点/虚词「的」切段，段间 AND（「中国西藏的雪山」→ 中国∩西藏∩雪山）
      const segments = q.split(/[\s,，、;；!！?？的]+/).filter(Boolean)
      if (segments.length) {
        const perSegment = segments.map((seg) => segmentScores(index, seg))
        const inter = perSegment.reduce(
          (acc, s) => new Set([...acc].filter((id) => s.has(id))),
          new Set(perSegment[0].keys()),
        )
        // 多段命中累加分数；同分保持原顺序（Array.sort 稳定，日期序不被打乱）
        const score = new Map()
        for (const s of perSegment)
          for (const [id, v] of s) if (inter.has(id)) score.set(id, (score.get(id) ?? 0) + v)
        result = result.filter((r) => inter.has(r.id)).sort((a, b) => score.get(b.id) - score.get(a.id))
      }
    }
  }
  kwCache = { index, records, query: q, result }
  return result
}

export function searchRecords(index, records, query, filters) {
  return applyFilters(keywordStage(index, records, query), filters)
}
