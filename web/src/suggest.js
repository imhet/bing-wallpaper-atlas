// 词典反查：查询词是某地名的某一种写法时，建议它的其他写法（零结果兜底）。
// aliasData 与 crawler/geo_aliases.json 同构（拷贝在 public/data/ 下，按需懒加载）。
export function suggestFromDict(query, aliasData) {
  const q = String(query).trim().toLowerCase()
  if (!q) return []
  for (const [name, alts] of Object.entries(aliasData)) {
    const group = [name, ...alts]
    if (group.some((a) => a.toLowerCase() === q)) {
      return group.filter((a) => a.toLowerCase() !== q).slice(0, 4)
    }
  }
  return []
}
