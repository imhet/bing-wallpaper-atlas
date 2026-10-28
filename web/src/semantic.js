// 语义检索的浏览器侧核心：分片解析、概念加权、图向量打分、关键词/语义 RRF 融合。
//
// 模型加载（bge 编码查询）与数据拉取不在这里——本文件只放可测的纯函数。
// 向量格式见 crawler/semantic_index.py：int8 + 每向量 scale，点积后再乘 scale 即余弦。

export const DIM = 512

const MAGIC = [66, 83, 69, 77] // "BSEM"

export function parseShard(buffer) {
  const bytes = new Uint8Array(buffer)
  if (bytes.length < 11 || MAGIC.some((b, i) => bytes[i] !== b)) throw new Error('不是语义向量分片')
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength)
  const dim = view.getUint16(5, true)
  const count = view.getUint32(7, true)
  if (bytes[4] !== 1) throw new Error(`向量分片版本不支持：v${bytes[4]}`)
  const dec = new TextDecoder()
  const rows = []
  let pos = 11
  for (let n = 0; n < count; n++) {
    const klen = bytes[pos]
    pos += 1
    const key = dec.decode(bytes.subarray(pos, pos + klen))
    pos += klen
    const scale = view.getFloat32(pos, true)
    pos += 4
    rows.push({ key, vec: Int8Array.from(bytes.subarray(pos, pos + dim)), scale })
    pos += dim
  }
  return rows
}

export function packShard(rows, dim = DIM) {
  const out = [new Uint8Array([...MAGIC, 1, dim & 0xff, dim >> 8, rows.length & 0xff, (rows.length >> 8) & 0xff, (rows.length >> 16) & 0xff, (rows.length >> 24) & 0xff])]
  const enc = new TextEncoder()
  for (const { key, vec, scale } of rows) {
    const kb = enc.encode(key)
    const head = new Uint8Array(1 + kb.length + 4)
    head[0] = kb.length
    head.set(kb, 1)
    new DataView(head.buffer).setFloat32(1 + kb.length, scale, true)
    out.push(head, new Uint8Array(vec.map((v) => v & 0xff)))
  }
  const total = out.reduce((n, p) => n + p.length, 0)
  const bytes = new Uint8Array(total)
  let pos = 0
  for (const p of out) {
    bytes.set(p, pos)
    pos += p.length
  }
  return bytes
}

const CLS_ID = 101
const SEP_ID = 102
const UNK_ID = 100

// bge-small-zh 用的是 BERT 词表：汉字逐字查表即可，不需要 WordPiece
// （中文一行一字，查询以中文为主；拉丁词查不到时会退化成单字母，语义变弱但不影响关键词结果）。
export function encodeQuery(text, vocab, maxLen = 32) {
  const ids = [CLS_ID]
  for (const ch of String(text).toLowerCase()) {
    if (/\s/.test(ch)) continue
    if (ids.length >= maxLen - 1) break
    ids.push(vocab.get(ch) ?? UNK_ID)
  }
  ids.push(SEP_ID)
  const inputIds = new BigInt64Array(maxLen)
  const mask = new BigInt64Array(maxLen)
  ids.forEach((id, i) => {
    inputIds[i] = BigInt(id)
    mask[i] = 1n
  })
  return { inputIds, mask, tokenTypeIds: new BigInt64Array(maxLen) }
}

// 从模型输出里取出句子向量：输出可能是 last_hidden_state（[1, seq, hidden]）或已池化的
// [1, hidden]，两种情况都只取第一行（CLS）——用整段归一化会把范数放大 sqrt(seq) 倍，
// 查询向量随之缩小，softmax 温度失效、概念权重被抹平。
export function pickQueryVector({ data, dims }) {
  const hidden = dims[dims.length - 1]
  const cls = data.subarray(0, hidden)
  let norm = 0
  for (let i = 0; i < hidden; i++) norm += cls[i] * cls[i]
  norm = Math.sqrt(norm) || 1
  return Float32Array.from(cls, (x) => x / norm)
}

// 查询向量与每个概念向量的余弦（概念已归一化，故乘 scale 即可）。
export function conceptSims(query, concepts) {
  const out = new Float32Array(concepts.length)
  for (let k = 0; k < concepts.length; k++) {
    const { vec, scale } = concepts[k]
    let dot = 0
    for (let j = 0; j < vec.length; j++) dot += query[j] * vec[j]
    out[k] = dot * scale
  }
  return out
}

// 概念桥接：查询落不到任何一个概念上（全负相关）时会选出最不差的几个，
// 权重趋近均匀——仍好过失配，因为图上分数由多个概念平均，不会偏向某一类。
export function pickConcepts(sims, topK, temp) {
  const order = [...sims.keys()].sort((a, b) => sims[b] - sims[a]).slice(0, topK)
  const exps = order.map((i) => Math.exp(sims[i] * temp))
  const sum = exps.reduce((a, b) => a + b, 0)
  return order.map((i, n) => ({ i, w: exps[n] / sum }))
}

// 图的语义分数 = 各概念余弦的加权和。
export function semanticRank(images, conceptsClip, picked) {
  const scores = new Map()
  for (const img of images) {
    let s = 0
    for (const { i, w } of picked) {
      const c = conceptsClip[i]
      let dot = 0
      for (let j = 0; j < img.vec.length; j++) dot += img.vec[j] * c.vec[j]
      s += w * dot * c.scale
    }
    scores.set(img.key, s * img.scale)
  }
  return scores
}

// 找相似的图：当前图组向量与全库做余弦（int8 点积 × 双 scale），排除自身取前 K。
// 只用图向量不碰语言模型，6770 图 × 512 维同步点积毫秒级；键不在库里（该组未编码）返回空数组
export function similarImages(rows, key, topK) {
  const self = rows.find((r) => r.key === key)
  if (!self) return []
  const scored = rows
    .filter((r) => r.key !== key)
    .map((r) => {
      let dot = 0
      for (let j = 0; j < self.vec.length; j++) dot += self.vec[j] * r.vec[j]
      return { key: r.key, score: dot * self.scale * r.scale }
    })
  scored.sort((a, b) => b.score - a.score)
  return scored.slice(0, topK)
}

// 图组归一键：与 favorites/imgKey 同口径（镜像记录的 urlbase 各市场路径不同，靠 imageKey 归一）
const groupKey = (r) => r.imageKey || r.urlbase.replace(/_[A-Z]{2}-[A-Z]{2}\d+$/, '')

// 语义候选的地理约束：CLIP 概念跨市场共享，「中国的秋景」的语义结果会混入日本秋景。
// 查询含地理限定词（extractGeoTerms）时三档处理——region 匹配 ×3 加权（霸住语义前排），
// 冲突 ×0.05 沉底（前 200 截断会挤掉它），未知保持原分（全库 55% 记录无 region，不冤枉）。
export function geoFilterSemScores(semScores, records, terms) {
  if (!terms.length) return semScores
  const termsSet = new Set(terms)
  const regionOf = new Map()
  for (const r of records) {
    const key = groupKey(r)
    if (!regionOf.has(key)) regionOf.set(key, r.region || '')
  }
  return new Map(
    [...semScores].map(([key, s]) => {
      const region = regionOf.get(key) || ''
      return [key, region ? (termsSet.has(region) ? s * 3 : s * 0.05) : s]
    }),
  )
}

// Reciprocal Rank Fusion：关键词名次与语义名次各自贡献 1/(k+rank)，语义独有结果得以进入列表
// （零结果查询靠它救回）。k=60 是 RRF 的常用默认值，评估集上已按同一参数验证过。
export function rrfFuse(records, keywordIds, semScores, { k = 60, semTopN = 200 } = {}) {
  // 语义分数覆盖全库（每张图都有分），只让前 N 名参与融合——
  // 否则零结果查询会显示「找到 6759 张」，用户看不出到底有没有命中。
  const semRank = new Map()
  ;[...semScores.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, semTopN)
    .forEach(([key], n) => semRank.set(key, n + 1))
  const kwRank = new Map(keywordIds.map((id, n) => [id, n + 1]))
  const scored = []
  for (const r of records) {
    const kw = kwRank.get(r.id)
    const sem = semRank.get(groupKey(r))
    if (kw === undefined && sem === undefined) continue
    scored.push({ r, s: (kw ? 1 / (k + kw) : 0) + (sem ? 1 / (k + sem) : 0) })
  }
  scored.sort((a, b) => b.s - a.s) // 稳定排序：同分保持候选集原顺序（日期倒序）
  return scored.map((x) => x.r)
}
