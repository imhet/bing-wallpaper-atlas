import { searchRecords } from './search'

// 分面计数：每个下拉的计数 = 「除自身外的其他筛选 + 搜索词」过滤后的分布（电商分面导航口径）。
// 选了 zh-cn，年份计数就是 zh-cn 内部的年份分布，各项之和正好等于该市场总数。
// 数据源是全量 records（首屏全量加载），与 aggregations.json 的静态全局统计无关。

// 各维度的取值提取：返回数组是因为分辨率是多值维度（一条记录可多档可用）。
// 空值（region/photographer 为空串）不产出选项，与旧 aggregations 的 counted 口径一致。
const EXTRACT = {
  market: (r) => [r.market],
  year: (r) => [r.date.slice(0, 4)],
  month: (r) => [String(Number(r.date.slice(5, 7)))], // '01' → '1'，与下拉 value 一致
  region: (r) => (r.region ? [r.region] : []),
  photographer: (r) => (r.photographer ? [r.photographer] : []),
  resolution: (r) =>
    Object.keys(r.resolutions || {}).filter((k) => k !== 'thumb' && r.resolutions[k]),
}

const RES_ORDER = ['uhd', 'fhd', 'hd']
const byName = (a, b) => String(a.name).localeCompare(String(b.name))
const ORDER = {
  market: byName,
  year: (a, b) => Number(a.name) - Number(b.name),
  month: (a, b) => Number(a.name) - Number(b.name),
  region: (a, b) => b.count - a.count || byName(a, b), // 计数降序，与旧 most_common 一致
  photographer: (a, b) => b.count - a.count || byName(a, b),
  resolution: (a, b) => RES_ORDER.indexOf(a.name) - RES_ORDER.indexOf(b.name),
}

export function computeFacets(index, records, query, filters) {
  const out = {}
  for (const dim of Object.keys(EXTRACT)) {
    const pool = searchRecords(index, records, query, { ...filters, [dim]: '' })
    const counts = new Map()
    for (const r of pool) for (const v of EXTRACT[dim](r)) counts.set(v, (counts.get(v) || 0) + 1)
    const cur = filters[dim] ? String(filters[dim]) : ''
    if (cur && !counts.has(cur)) counts.set(cur, 0) // 选中值被筛空时保留，防 select 显示错位
    out[dim] = [...counts.entries()].map(([name, count]) => ({ name, count })).sort(ORDER[dim])
  }
  return out
}
