import { describe, expect, it } from 'vitest'
import { encodeQuery, geoFilterSemScores, packShard, parseShard, pickConcepts, pickQueryVector, rrfFuse, semanticRank, similarImages } from './semantic'
import { extractGeoTerms } from './search'

// 构造与 crawler/semantic_index.py 相同的分片格式：BSEM | v1 | dim | count | [klen|key|scale|int8[dim]]
function shard(rows, dim = 4) {
  const enc = new TextEncoder()
  const parts = [new Uint8Array([66, 83, 69, 77, 1, dim, 0, rows.length, 0, 0, 0])]
  for (const [key, vec, scale] of rows) {
    const kb = enc.encode(key)
    const head = new Uint8Array(1 + kb.length + 4)
    head[0] = kb.length
    head.set(kb, 1)
    new DataView(head.buffer).setFloat32(1 + kb.length, scale, true)
    parts.push(head, new Uint8Array(vec.map((v) => v & 0xff)))
  }
  const total = parts.reduce((n, p) => n + p.length, 0)
  const out = new Uint8Array(total)
  let pos = 0
  for (const p of parts) {
    out.set(p, pos)
    pos += p.length
  }
  return out
}

describe('parseShard', () => {
  it('reads keys, int8 vectors and scales in order', () => {
    const buf = shard([
      ['ChambordCastle', [1, -2, 3, -4], 0.5],
      ['https://x/y.jpg', [0, 0, 0, 0], 0],
    ])
    const rows = parseShard(buf)
    expect(rows.map((r) => r.key)).toEqual(['ChambordCastle', 'https://x/y.jpg'])
    expect([...rows[0].vec]).toEqual([1, -2, 3, -4])
    expect(rows[0].scale).toBeCloseTo(0.5)
  })

  it('rejects a buffer that is not a semantic shard', () => {
    expect(() => parseShard(new Uint8Array([1, 2, 3]))).toThrow(/分片/)
  })

  it('round-trips through packShard', () => {
    const rows = [{ key: '灯塔', vec: Int8Array.from([-128, 1, 2]), scale: 0.25 }]
    expect(parseShard(packShard(rows, 3))).toEqual(rows)
  })
})

describe('pickConcepts', () => {
  // 查询向量与 4 个概念的点积：只有第 1、3 个概念相近
  const sims = [0.9, 0.1, 0.7, -0.2]

  it('returns softmax weights over the top-k concepts, summing to 1', () => {
    const picked = pickConcepts(sims, 2, 12)
    expect(picked.map((p) => p.i)).toEqual([0, 2])
    expect(picked.reduce((s, p) => s + p.w, 0)).toBeCloseTo(1)
    expect(picked[0].w).toBeGreaterThan(picked[1].w)
  })

  it('falls back to all concepts when top-k exceeds the concept count', () => {
    expect(pickConcepts(sims, 10, 12)).toHaveLength(4)
  })
})

describe('semanticRank', () => {
  // 概念「灯塔」：图 0 与之相近，图 1 与「雪山」相近
  const images = [
    { key: 'lighthouse', vec: Int8Array.from([127, 0, 0, 0]), scale: 1 / 127 },
    { key: 'mountain', vec: Int8Array.from([0, 0, 127, 0]), scale: 1 / 127 },
  ]
  const conceptsClip = [
    { vec: Int8Array.from([127, 0, 0, 0]), scale: 1 / 127 },
    { vec: Int8Array.from([127, 0, 0, 0]), scale: 1 / 127 },
    { vec: Int8Array.from([0, 0, 127, 0]), scale: 1 / 127 },
    { vec: Int8Array.from([0, 0, 0, 127]), scale: 1 / 127 },
  ]

  it('scores images by similarity to the weighted concept set', () => {
    const weights = pickConcepts([0.9, 0.1, 0.7, -0.2], 2, 12)
    const scores = semanticRank(images, conceptsClip, weights)
    expect(scores.get('lighthouse')).toBeGreaterThan(scores.get('mountain'))
  })
})

describe('encodeQuery', () => {
  const vocab = new Map([['灯', 7], ['塔', 8], ['a', 9]])

  it('wraps characters in CLS/SEP and pads the rest with zeros', () => {
    const { inputIds, mask } = encodeQuery('灯塔', vocab, 6)
    expect([...inputIds]).toEqual([101n, 7n, 8n, 102n, 0n, 0n])
    expect([...mask]).toEqual([1n, 1n, 1n, 1n, 0n, 0n])
  })

  it('maps unknown characters to UNK and ignores whitespace', () => {
    const { inputIds } = encodeQuery('灯 火', vocab, 6)
    expect([...inputIds]).toEqual([101n, 7n, 100n, 102n, 0n, 0n])
  })

  it('truncates long queries so SEP still fits', () => {
    const { inputIds } = encodeQuery('灯塔灯塔灯塔灯塔', vocab, 4)
    expect([...inputIds]).toEqual([101n, 7n, 8n, 102n])
  })
})

describe('pickQueryVector', () => {
  it('takes only the CLS row from a [1, seq, hidden] output and normalizes it', () => {
    // 模型输出 last_hidden_state（1×2×3），只有第一行是句子向量。
    // 拿整段归一化会把范数放大约 sqrt(seq) 倍，查询向量被缩小、概念权重被抹平。
    const data = Float32Array.from([3, 4, 0, 0, 100, 0])
    const vec = pickQueryVector({ data, dims: [1, 2, 3] })
    expect(vec[0]).toBeCloseTo(0.6)
    expect(vec[1]).toBeCloseTo(0.8)
    expect(vec[2]).toBeCloseTo(0)
  })

  it('handles an already-pooled [1, hidden] output', () => {
    const data = Float32Array.from([0, 0.5])
    expect([...pickQueryVector({ data, dims: [1, 2] })]).toEqual([0, 1])
  })
})

describe('rrfFuse', () => {
  const rec = (id, key) => ({ id, imageKey: key, urlbase: '/th?id=' + key })

  it('promotes a record that ranks well in both lists', () => {
    // 关键词第 1 的 A 与「关键词第 2 + 语义第 1」的 B 对照：B 两个信号都在，应反超
    const records = [rec('a', 'A'), rec('b', 'B'), rec('c', 'C')]
    const keyword = ['a', 'b', 'c']
    const fused = rrfFuse(records, keyword, new Map([['B', 1]]), { k: 60 })
    expect(fused.map((r) => r.id)).toEqual(['b', 'a', 'c'])
  })

  it('includes records found only by semantics', () => {
    const records = [rec('a', 'A'), rec('b', 'B')]
    const fused = rrfFuse(records, ['a'], new Map([['B', 1]]), { k: 60 })
    expect(fused.map((r) => r.id).sort()).toEqual(['a', 'b'])
  })

  it('only admits the strongest N semantic hits', () => {
    // 语义会给全库每张图打分，全收进来会让「找到 6759 张」淹没真正的命中。
    // 只让语义前 N 名参与融合：零结果查询的结果数 = N，而不是全库大小。
    const records = [rec('a', 'A'), rec('b', 'B'), rec('c', 'C')]
    const sem = new Map([['A', 0.9], ['B', 0.8], ['C', 0.1]])
    expect(rrfFuse(records, [], sem, { semTopN: 2 }).map((r) => r.id)).toEqual(['a', 'b'])
  })

  it('keeps keyword order when every semantic score is absent', () => {
    const records = [rec('a', 'A'), rec('b', 'B')]
    const fused = rrfFuse(records, ['b', 'a'], new Map(), { k: 60 })
    expect(fused.map((r) => r.id)).toEqual(['b', 'a'])
  })
})

describe('similarImages（图组间的余弦近邻）', () => {
  // A 的近邻是 B（几乎同向），C/D 正交更远
  const rows = [
    { key: 'A', vec: Int8Array.from([127, 0, 0, 0]), scale: 1 / 127 },
    { key: 'B', vec: Int8Array.from([126, 12, 0, 0]), scale: 1 / Math.hypot(126, 12) },
    { key: 'C', vec: Int8Array.from([0, 127, 0, 0]), scale: 1 / 127 },
    { key: 'D', vec: Int8Array.from([0, 0, 127, 0]), scale: 1 / 127 },
  ]

  it('按余弦降序返回前 K 个且排除自身', () => {
    expect(similarImages(rows, 'A', 2).map((x) => x.key)).toEqual(['B', 'C'])
    expect(similarImages(rows, 'A', 10).map((x) => x.key)).toEqual(['B', 'C', 'D'])
  })

  it('分数是与自身向量的余弦（乘双 scale）', () => {
    const out = similarImages(rows, 'B', 1)
    expect(out[0].key).toBe('A')
    expect(out[0].score).toBeCloseTo((126 * 127) / (127 * Math.hypot(126, 12)), 5)
  })

  it('键不存在时返回空数组（该图组未编码向量）', () => {
    expect(similarImages(rows, 'missing', 5)).toEqual([])
  })
})

describe('extractGeoTerms（查询里的地理限定段）', () => {
  it('只有完整等于某个 region 值的段才算地理限定', () => {
    // 「中国的秋景」切段 [中国, 秋景]，只有「中国」是 region 值
    expect(extractGeoTerms('中国的秋景', ['中国', '美国', '日本'])).toEqual(['中国'])
    expect(extractGeoTerms('中国 雪山', ['中国', '美国'])).toEqual(['中国'])
    expect(extractGeoTerms('秋景', ['中国'])).toEqual([])
    expect(extractGeoTerms('', ['中国'])).toEqual([])
  })
})

describe('geoFilterSemScores（语义候选的地理约束）', () => {
  // 语义（CLIP 概念）不懂国别：「中国的秋景」的语义结果会混入日本秋景，需按 region 约束
  const recs = [
    { id: 'cn-1', imageKey: 'A', region: '中国', urlbase: '/th?id=A' },
    { id: 'jp-1', imageKey: 'B', region: '日本', urlbase: '/th?id=B' },
    { id: 'xx-1', imageKey: 'C', region: null, urlbase: '/th?id=C' },
  ]

  it('region 与地理词冲突的图衰减沉底，匹配的加权，未知的保留原分', () => {
    const out = geoFilterSemScores(new Map([['A', 0.9], ['B', 0.95], ['C', 0.8]]), recs, ['中国'])
    expect(out.get('A')).toBe(2.7) // 匹配 ×3：region=中国 的图霸住语义前排
    expect(out.get('C')).toBe(0.8) // region 未知不惩罚
    expect(out.get('B')).toBeLessThan(0.05)
  })

  it('无地理词时原样返回', () => {
    const scores = new Map([['A', 0.9]])
    expect(geoFilterSemScores(scores, recs, [])).toBe(scores)
  })

  it('融合后中国图排到日本图前面（「中国的秋景」端到端）', () => {
    const records = [
      { id: 'cn', imageKey: 'A', region: '中国', urlbase: '/th?id=A' },
      { id: 'jp', imageKey: 'B', region: '日本', urlbase: '/th?id=B' },
    ]
    const sem = geoFilterSemScores(new Map([['A', 0.9], ['B', 0.95]]), records, ['中国'])
    expect(rrfFuse(records, [], sem, { k: 60 }).map((r) => r.id)).toEqual(['cn', 'jp'])
  })
})
