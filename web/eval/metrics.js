// 检索质量指标。输入是检索返回的 id 序列（按排名）与人工/LLM 判定的
// id→相关性(0/1/2) 表。池内无相关文档的查询返回 null，由调用方跳过聚合，
// 避免「该查询没有可评估对象」被算成 0 分拉低整体。

const gain = (rel) => 2 ** rel - 1

function dcg(ids, judgments, k) {
  let sum = 0
  for (let i = 0; i < Math.min(ids.length, k); i++) sum += gain(judgments.get(ids[i]) ?? 0) / Math.log2(i + 2)
  return sum
}

export function ndcgAtK(rankedIds, judgments, k = 10) {
  const ideal = [...judgments.values()].filter((r) => r > 0).sort((a, b) => b - a)
  if (!ideal.length) return null
  const idcg = ideal.slice(0, k).reduce((s, rel, i) => s + gain(rel) / Math.log2(i + 2), 0)
  return dcg(rankedIds, judgments, k) / idcg
}

export function recallAtK(rankedIds, judgments, k = 20) {
  const relevant = [...judgments.entries()].filter(([, r]) => r > 0).map(([id]) => id)
  if (!relevant.length) return null
  const top = new Set(rankedIds.slice(0, k))
  return relevant.filter((id) => top.has(id)).length / relevant.length
}

export function mrrAtK(rankedIds, judgments, k = 10) {
  for (let i = 0; i < Math.min(rankedIds.length, k); i++)
    if ((judgments.get(rankedIds[i]) ?? 0) > 0) return 1 / (i + 1)
  return 0
}

export function zeroResultRate(resultSets) {
  if (!resultSets.length) return 0
  return resultSets.filter((ids) => !ids.length).length / resultSets.length
}

export function jaccard(a, b) {
  const A = new Set(a)
  const B = new Set(b)
  const inter = [...A].filter((x) => B.has(x)).length
  const union = A.size + B.size - inter
  return union ? inter / union : 1
}
