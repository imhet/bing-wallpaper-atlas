import { describe, expect, it } from 'vitest'
import { encodeQuery, packShard, parseShard, pickConcepts, pickQueryVector, rrfFuse, semanticRank } from './semantic'

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
