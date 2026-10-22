// 基线评测：跑线上同一套 web/src/search.js，对 web/eval/queries.json 的 100 条
// 查询计算 nDCG@10 / Recall@50 / MRR@10 / 零结果率。
//
// 比对在图组空间（imageKey）进行：同一张图的不同市场版本算一个结果，
// 与 App.vue 的 dedupeByUrlbase 显示口径一致。
//
// 用法：node eval/run_eval.mjs [--json]
import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { dedupeByUrlbase, imgKey } from '../src/api.js'
import { buildIndex, searchRecords } from '../src/search.js'
import { mrrAtK, ndcgAtK, recallAtK, zeroResultRate } from './metrics.js'

const HERE = dirname(fileURLToPath(import.meta.url))
const ROOT = join(HERE, '..', '..')
const DATA = join(ROOT, 'data')

const agg = JSON.parse(readFileSync(join(DATA, 'aggregations.json'), 'utf8'))
const records = Object.entries(agg.years_by_market).flatMap(([market, years]) =>
  years.flatMap((y) => JSON.parse(readFileSync(join(DATA, market, `${y}.json`), 'utf8'))),
)
const queries = JSON.parse(readFileSync(join(HERE, 'queries.json'), 'utf8'))
// 池化判定（judge.py 生成）：候选池里被判定过的记录也进 qrels，
// 否则用户实际看到但没判过的相关结果会被当成不相关
const judged = existsSync(join(HERE, 'judgments.json'))
  ? JSON.parse(readFileSync(join(HERE, 'judgments.json'), 'utf8'))
  : {}
const NOSORT = process.argv.includes('--nosort') // 对照：复现「只过滤不排序」的旧行为

const groupKey = (r) => r.imageKey || imgKey(r.urlbase)
const keyById = new Map(records.map((r) => [r.id, groupKey(r)]))

const t0 = Date.now()
const index = buildIndex(records)
const buildMs = Date.now() - t0

if (process.argv.includes('--dump-candidates')) {
  // 池化判定用：每条查询的前 20 条（去重后）交给 judge.py 判相关度
  const dump = queries.map((item) => {
    const ids = dedupeByUrlbase(searchRecords(index, records, item.query, {})).slice(0, 20).map((r) => r.id)
    return { query: item.query, anchors: item.anchors, candidates: ids }
  })
  writeFileSync(join(HERE, 'candidates.json'), JSON.stringify(dump, null, 1) + '\n', 'utf8')
  console.log(`候选池已写入 eval/candidates.json（${dump.length} 条查询）`)
  process.exit(0)
}

const rows = queries.map((item) => {
  const anchors = [...new Set(item.anchors.map((id) => keyById.get(id)).filter(Boolean))]
  const missing = item.anchors.length - anchors.length
  const judgments = new Map(anchors.map((k) => [k, 2]))
  for (const [id, rel] of Object.entries(judged[item.query] || {})) {
    const k = keyById.get(id)
    if (k) judgments.set(k, Math.max(judgments.get(k) ?? 0, rel))
  }

  const t = Date.now()
  const ranked = searchRecords(index, records, item.query, {})
  const pool = NOSORT ? records.filter((r) => new Set(ranked.map((x) => x.id)).has(r.id)) : ranked
  const hits = dedupeByUrlbase(pool).map(groupKey)
  const ms = Date.now() - t

  return {
    query: item.query,
    category: item.category,
    anchors: anchors.length,
    missingAnchors: missing,
    hits: hits.length,
    ms,
    ndcg: ndcgAtK(hits, judgments, 10),
    // 集合召回不设 K：线上全部命中都可滚动到底，K 截断会把「排序差」误记成「找不到」
    setRecall: recallAtK(hits, judgments, Infinity),
    recall: recallAtK(hits, judgments, 50),
    mrr: mrrAtK(hits, judgments, 10),
  }
})

const mean = (xs) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0)
const summarize = (rs) => ({
  n: rs.length,
  ndcg: mean(rs.map((r) => r.ndcg).filter((v) => v !== null)),
  setRecall: mean(rs.map((r) => r.setRecall).filter((v) => v !== null)),
  recall: mean(rs.map((r) => r.recall).filter((v) => v !== null)),
  mrr: mean(rs.map((r) => r.mrr).filter((v) => v !== null)),
  zero: zeroResultRate(rs.map((r) => (r.hits ? [1] : []))),
  ms: mean(rs.map((r) => r.ms)),
})

const cats = ['literal', 'synonym', 'intent', 'free']
const report = { buildMs, total: summarize(rows), byCategory: {}, rows }
for (const c of cats) report.byCategory[c] = summarize(rows.filter((r) => r.category === c))

if (process.argv.includes('--json')) {
  console.log(JSON.stringify(report, null, 1))
} else {
  const pct = (v) => (v * 100).toFixed(1).padStart(6) + '%'
  console.log(`索引构建 ${buildMs}ms，记录 ${records.length} 条，查询 ${rows.length} 条\n`)
  console.log('类别      查询   nDCG@10   集合召回   MRR@10   零结果   均耗时')
  for (const c of cats) {
    const s = report.byCategory[c]
    console.log(
      `${c.padEnd(9)} ${String(s.n).padStart(4)}   ${pct(s.ndcg)}   ${pct(s.setRecall)}   ${pct(s.mrr)}   ${pct(s.zero)}   ${s.ms.toFixed(0).padStart(5)}ms`,
    )
  }
  const t = report.total
  console.log(`${'总计'.padEnd(8)} ${String(t.n).padStart(4)}   ${pct(t.ndcg)}   ${pct(t.setRecall)}   ${pct(t.mrr)}   ${pct(t.zero)}   ${t.ms.toFixed(0).padStart(5)}ms`)

  const worst = [...rows].sort((a, b) => (a.ndcg ?? 1) - (b.ndcg ?? 1)).slice(0, 15)
  console.log('\n最差 15 条：')
  for (const r of worst)
    console.log(
      `  ${(r.ndcg ?? -1).toFixed(3)}  ${r.category.padEnd(8)} 「${r.query}」 命中 ${r.hits} / 锚点 ${r.anchors}`,
    )
  const zeroRows = rows.filter((r) => !r.hits)
  if (zeroRows.length) console.log(`\n零结果 ${zeroRows.length} 条：${zeroRows.map((r) => r.query).join('、')}`)
}

writeFileSync(join(HERE, 'baseline.json'), JSON.stringify(report, null, 1) + '\n', 'utf8')
console.log('\n明细已写入 eval/baseline.json')
