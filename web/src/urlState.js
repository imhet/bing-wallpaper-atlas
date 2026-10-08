// 筛选状态 ↔ URL query 同步：分享链接、刷新还原都靠它。
// query→q 缩短；空值不进 URL；year/month 还原为数字，垃圾值安全降级为空。

const FIELDS = ['market', 'region', 'photographer', 'resolution']

export function encodeFilters(f) {
  const p = new URLSearchParams()
  if (f.query) p.set('q', f.query)
  if (f.market) p.set('market', f.market)
  if (f.year) p.set('year', String(f.year))
  if (f.month) p.set('month', String(f.month))
  for (const k of FIELDS) if (f[k]) p.set(k, f[k])
  const s = p.toString()
  return s ? `?${s}` : ''
}

export function decodeFilters(search) {
  const p = new URLSearchParams(search)
  const num = (k) => {
    const v = p.get(k)
    return v && Number.isFinite(Number(v)) ? Number(v) : ''
  }
  const out = { query: p.get('q') || '', year: num('year'), month: num('month') }
  for (const k of FIELDS) out[k] = p.get(k) || ''
  return out
}
