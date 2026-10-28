// 语义引擎加载层：拉模型与向量分片、跑 bge 推理、产出图组分数。
//
// 首屏不依赖这里——调用方在空闲时启动，关键词结果先出，语义就绪后再重排；
// 任何一步失败都只是让页面退回纯关键词，不影响可用性。

import * as ort from 'onnxruntime-web/wasm'
import { conceptSims, encodeQuery, parseShard, pickConcepts, pickQueryVector, semanticRank, similarImages } from './semantic'

ort.env.wasm.numThreads = 1 // 多线程要 SharedArrayBuffer，Pages 没有 COOP/COEP 头

const BASE = './data/sem'
// 国内直连 github.io 只有几十 KB/s，模型和 wasm 从 jsDelivr 取（免费、有国内节点）；
// jsDelivr 取不到时回退到 Pages 上的同一份文件，两条路都不通就退回纯关键词检索。
const CDN = 'https://cdn.jsdelivr.net'
const REPO = `${CDN}/gh/imhet/bing-wallpaper-atlas@main`
const MODEL_CDN = `${REPO}/data/sem/bge/model_4bit.onnx`
const WASM_CDN = `${REPO}/data/sem/ort/ort-wasm-simd-threaded.wasm`
const WASM_LOCAL = new URL(`${BASE}/ort/ort-wasm-simd-threaded.wasm`, location.href).href
const MAX_LEN = 32
const TOP_K_CONCEPTS = 3 // 与评估集上选出的最优参数一致
const CONCEPT_TEMP = 12

async function fetchArrayBuffer(path) {
  const resp = await fetch(path)
  if (!resp.ok) throw new Error(`${path}: HTTP ${resp.status}`)
  return resp.arrayBuffer()
}

// CDN 是否可用用 HEAD 预检：失败时只等几秒就能回退，而不是把整个文件的下载超时等完。
async function reachable(url, timeoutMs = 5000) {
  try {
    const resp = await fetch(url, { method: 'HEAD', signal: AbortSignal.timeout(timeoutMs) })
    return resp.ok
  } catch {
    return false
  }
}

async function loadImageShards(years) {
  const rows = []
  await Promise.all(
    years.map(async (year) => {
      try {
        rows.push(...parseShard(await fetchArrayBuffer(`${BASE}/${year}.bin`)))
      } catch {
        // 该年无分片或已损坏：少一年的图不参与语义检索，其余照常
      }
    }),
  )
  return rows
}

// 找相似的图只需要图向量，不碰语言模型——单独建索引，语义模型加载失败也不影响它
export async function createSimilarIndex({ years = [] } = {}) {
  const images = await loadImageShards(years)
  if (!images.length) throw new Error('无图向量分片')
  return {
    size: images.length,
    similar(key, topK) {
      return similarImages(images, key, topK)
    },
  }
}

export async function createSemanticEngine({ years = [], onProgress = () => {} } = {}) {
  onProgress('词汇表')
  const vocab = new Map(
    (await (await fetch(`${BASE}/bge/vocab.txt`)).text()).split('\n').map((w, i) => [w.trim(), i]),
  )

  onProgress('概念向量')
  const [conceptsClip, conceptsBge] = await Promise.all(
    [fetchArrayBuffer(`${BASE}/concepts_clip.bin`), fetchArrayBuffer(`${BASE}/concepts_bge.bin`)].map((p) =>
      p.then(parseShard),
    ),
  )

  onProgress('图向量')
  const images = await loadImageShards(years)

  onProgress('语言模型')
  const [modelFromCdn, wasmFromCdn] = await Promise.all([reachable(MODEL_CDN), reachable(WASM_CDN)])
  const model = await fetchArrayBuffer(modelFromCdn ? MODEL_CDN : `${BASE}/bge/model_4bit.onnx`)
  ort.env.wasm.wasmPaths = { wasm: wasmFromCdn ? WASM_CDN : WASM_LOCAL }
  const session = await ort.InferenceSession.create(model, { executionProviders: ['wasm'] })
  const outputName = session.outputNames[0]

  async function embed(text) {
    const { inputIds, mask, tokenTypeIds } = encodeQuery(text, vocab, MAX_LEN)
    const out = await session.run({
      input_ids: new ort.Tensor('int64', inputIds, [1, MAX_LEN]),
      attention_mask: new ort.Tensor('int64', mask, [1, MAX_LEN]),
      token_type_ids: new ort.Tensor('int64', tokenTypeIds, [1, MAX_LEN]),
    })
    return pickQueryVector(out[outputName])
  }

  return {
    size: images.length,
    async rank(query) {
      const q = await embed(query)
      const picked = pickConcepts(conceptSims(q, conceptsBge), TOP_K_CONCEPTS, CONCEPT_TEMP)
      return semanticRank(images, conceptsClip, picked)
    },
  }
}
