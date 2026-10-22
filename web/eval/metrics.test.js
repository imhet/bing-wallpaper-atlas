import { describe, expect, it } from 'vitest'
import { jaccard, mrrAtK, ndcgAtK, recallAtK, zeroResultRate } from './metrics'

// 手算样本：a 完全相关(2)、b/d 部分相关(1)、c 不相关(0)
const JUDGED = new Map([
  ['a', 2],
  ['b', 1],
  ['c', 0],
  ['d', 1],
])

describe('ndcgAtK', () => {
  it('完美排序为 1', () => {
    expect(ndcgAtK(['a', 'b', 'd', 'c'], JUDGED, 10)).toBeCloseTo(1, 6)
  })

  it('不理想排序按 2^rel-1 增益与 log2 折损计算', () => {
    // DCG = 3/1 + 0/log2(3) + 1/log2(4) + 1/log2(5) = 3.9307
    // IDCG = 3/1 + 1/log2(3) + 1/log2(4) = 4.1309
    expect(ndcgAtK(['a', 'c', 'b', 'd'], JUDGED, 10)).toBeCloseTo(0.9515, 3)
  })

  it('只计入 k 名以内', () => {
    expect(ndcgAtK(['c', 'c', 'a'], JUDGED, 2)).toBe(0)
  })

  it('未判定的 id 视为 0 分，且不进入 IDCG 分母', () => {
    // 多返回一个未判定 id 不应改变 DCG 或 IDCG（池内相关文档数固定为 3）
    expect(ndcgAtK(['a', 'z'], JUDGED, 10)).toBeCloseTo(ndcgAtK(['a'], JUDGED, 10), 6)
    expect(ndcgAtK(['a'], JUDGED, 10)).toBeCloseTo(3 / (3 + 1 / Math.log2(3) + 1 / Math.log2(4)), 6)
  })

  it('池内无相关文档时返回 null（该查询不参与聚合）', () => {
    expect(ndcgAtK(['c'], new Map([['c', 0]]), 10)).toBeNull()
  })
})

describe('recallAtK', () => {
  it('命中池内相关文档的比例', () => {
    // 相关 3 个（a,b,d），前 2 名命中 a,b
    expect(recallAtK(['a', 'b', 'c'], JUDGED, 2)).toBeCloseTo(2 / 3, 6)
  })

  it('分母为池内全部 rel>=1 文档，不是 k', () => {
    expect(recallAtK(['a'], JUDGED, 20)).toBeCloseTo(1 / 3, 6)
  })

  it('池内无相关文档时返回 null', () => {
    expect(recallAtK(['c'], new Map([['c', 0]]), 20)).toBeNull()
  })
})

describe('mrrAtK', () => {
  it('第一个相关结果在首位时为 1', () => {
    expect(mrrAtK(['a', 'b'], JUDGED, 10)).toBe(1)
  })

  it('第一个相关结果在第 3 位时为 1/3', () => {
    expect(mrrAtK(['c', 'c', 'd'], JUDGED, 10)).toBeCloseTo(1 / 3, 6)
  })

  it('k 名内无相关结果为 0', () => {
    expect(mrrAtK(['c', 'c', 'a'], JUDGED, 2)).toBe(0)
  })
})

describe('zeroResultRate', () => {
  it('零结果查询占比', () => {
    expect(zeroResultRate([[], ['a'], [], ['b']])).toBe(0.5)
  })

  it('无查询时返回 0 而不是 NaN', () => {
    expect(zeroResultRate([])).toBe(0)
  })
})

describe('jaccard', () => {
  it('集合交并比', () => {
    expect(jaccard(['a', 'b'], ['b', 'c'])).toBeCloseTo(1 / 3, 6)
  })

  it('两个空集视为完全一致', () => {
    expect(jaccard([], [])).toBe(1)
  })
})
