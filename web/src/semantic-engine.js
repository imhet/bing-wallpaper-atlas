// 语义引擎加载层：拉模型与向量分片、跑 bge 推理、产出图组分数。
//
// 首屏不依赖这里——调用方在空闲时启动，关键词结果先出，语义就绪后再重排；
// 任何一步失败都只是让页面退回纯关键词，不影响可用性。

import * as ort from 'onnxruntime-web/wasm'
import wasmUrl from 'onnxruntime-web/ort-wasm-simd-threaded.wasm?url'
import { conceptSims, encodeQuery, parseShard, pickConcepts, pickQueryVector, semanticRank } from './semantic'

ort.env.wasm.numThreads = 1 // 多线程要 SharedArrayBuffer，Pages 没有 COOP/COEP 头

const BASE = './data/sem'
// 国内直连 github.io 只有几十 KB/s，模型和 wasm 从 jsDelivr 取（免费、有国内节点）；
// jsDelivr 取不到时回退到 Pages 上的同一份文件，两条路都不通就退回纯关键词检索。
const CDN = 'https://cdn.jsdelivr.net'
const MODEL_CDN = `${CDN}/gh/imhet/bing-wallpaper-atlas@main/data/sem/bge/model_4bit.onnx`
const WASM_CDN = `${CDN}/npm/onnxruntime-web@1.30.0/dist/ort-wasm-simd-threaded.wasm`
const WASM_LOCAL = new URL(wasmUrl, location.href).href
const MAX_LEN = 32
const TOP_K_CONCEPTS = 3 // 与评估集上选出的最优参数一致
const CONCEPT_TEMP = 12

async function fetchArrayBuffer(path) {
  const resp = await fetch(path)
  if (!resp.ok) throw new Error(`${path}: HTTP ${resp.status}`)
  return resp.arrayBuffer()
}

// 按顺序尝试多个来源，全失败才抛错。CDN 返回错的文件（比如 404 页面）也会被 .ok 挡掉。
async function fetchFirst(paths) {
  let last
  for (const path of paths) {
    try {
      return await fetchArrayBuffer(path)
    } catch (e) {
      last = e
    }
  }
  throw last
}

async function pickWasmPath() {
  try {
    const resp = await fetch(WASM_CDN, { method: 'HEAD' })
    if (resp.ok) return WASM_CDN
  } catch {
    // 探测失败只是慢一点，不阻塞
  }
  return WASM_LOCAL
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
  const model = await fetchFirst([MODEL_CDN, `${BASE}/bge/model_4bit.onnx`])
  ort.env.wasm.wasmPaths = { wasm: await pickWasmPath() }
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
