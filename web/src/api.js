export const BING_BASE = 'https://www.bing.com'
export const RES_SUFFIX = { uhd: '_UHD.jpg', fhd: '_1920x1080.jpg', hd: '_1366x768.jpg' }

export const imageUrl = (urlbase, suffix) => `${BING_BASE}${urlbase}${suffix}`

export const thumbUrl = (r) =>
  r.resolutions?.thumb ? imageUrl(r.urlbase, '_400x240.jpg') : imageUrl(r.urlbase, '_1920x1080.jpg')

export async function fetchJSON(url) {
  const resp = await fetch(url)
  if (!resp.ok) throw new Error(`${url}: HTTP ${resp.status}`)
  return resp.json()
}

export const loadAggregations = () => fetchJSON('./data/aggregations.json')
export const loadShard = (market, year) => fetchJSON(`./data/${market}/${year}.json`)

export async function loadYearShards(aggregations, year) {
  const jobs = []
  for (const [market, years] of Object.entries(aggregations.years_by_market || {}))
    if (years.includes(Number(year))) jobs.push(loadShard(market, Number(year)))
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
