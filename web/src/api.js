export const BING_BASE = 'https://www.bing.com'
export const RES_SUFFIX = { uhd: '_UHD.jpg', fhd: '_1920x1080.jpg', hd: '_1366x768.jpg' }

// urlbase 两种形态：/th 开头 = Bing CDN 相对路径；https:// = 第三方镜像绝对 URL
// （npanuhin 深史源，老图无 OHR ID、无多档变体，原图即唯一档）
export const imageUrl = (urlbase, suffix) =>
  urlbase.startsWith('https://') ? urlbase : `${BING_BASE}${urlbase}${suffix}`

// 镜像记录（npanuhin 深史）网格用本地预生成的 480 宽 webp（gen_thumbs.py 产物，Actions
// 缓存随 Pages 分发）——原图 74~339KB 且无边缘缓存，直接当缩略图太慢；详情弹层大图仍直链原图
export const thumbUrl = (r) =>
  r.urlbase.startsWith('https://')
    ? `./data/thumbs/${r.market}/${r.date.slice(0, 4)}/${r.date}.webp`
    : r.resolutions?.thumb
      ? imageUrl(r.urlbase, '_400x240.jpg')
      : imageUrl(r.urlbase, '_1920x1080.jpg')

export async function fetchJSON(url) {
  const resp = await fetch(url)
  if (!resp.ok) throw new Error(`${url}: HTTP ${resp.status}`)
  return resp.json()
}

export const loadAggregations = () => fetchJSON('./data/aggregations.json')
export const loadShard = (market, year) => fetchJSON(`./data/${market}/${year}.json`)

export async function loadYearShards(aggregations, year, markets = null) {
  const jobs = []
  for (const [market, years] of Object.entries(aggregations.years_by_market || {}))
    if (years.includes(Number(year)) && (!markets || markets.includes(market)))
      jobs.push(loadShard(market, Number(year)))
  const shards = await Promise.all(jobs)
  return shards.flat()
}

export async function loadAllRecords(aggregations) {
  const jobs = []
  for (const [market, years] of Object.entries(aggregations.years_by_market || {}))
    for (const year of years) jobs.push(loadShard(market, year))
  const shards = await Promise.all(jobs)
  // 日期倒序：默认「全部年份」时最新壁纸在前，搜索结果也按最新优先
  return shards.flat().sort((a, b) => b.date.localeCompare(a.date))
}

// 同一天 Bing 全球各市场发同一张图（urlbase 仅市场后缀不同）——渲染层按图去重，
// 避免网格出现多张重复图。数据层不动：各市场版本仍是完整记录，计数保持记录口径。
const MARKET_PRIORITY = ['zh-cn', 'en-us', 'zh-tw']
const marketRank = (m) => {
  const i = MARKET_PRIORITY.indexOf(m)
  return i === -1 ? MARKET_PRIORITY.length : i
}

export const imgKey = (urlbase) => urlbase.replace(/_[A-Z]{2}-[A-Z]{2}\d+$/, '')

export function dedupeByUrlbase(records) {
  // Map 保插入序（= 组首次出现序，date 倒序语义不丢）；代表记录按市场优先序取
  const best = new Map()
  for (const r of records) {
    const key = imgKey(r.urlbase)
    const cur = best.get(key)
    if (!cur || marketRank(r.market) < marketRank(cur.market) || (marketRank(r.market) === marketRank(cur.market) && r.market < cur.market))
      best.set(key, r)
  }
  return [...best.values()]
}
