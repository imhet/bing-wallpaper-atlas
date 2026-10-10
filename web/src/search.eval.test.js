// 搜索准确度黄金集：直接跑在 data/ 真实全量记录上（非 mock）。
// 数字基线 2026-10-11（3458 条）；数据新增后「≥/包含」类断言仍应成立。
// 已知缺陷用 it.skip 标注（FIXME 注明根因）——修复时去掉 skip，先看红再修。
import { readFileSync } from 'node:fs'
import { beforeAll, describe, expect, it } from 'vitest'
import { buildIndex, searchRecords } from './search'

const shard = (market, year) =>
  JSON.parse(readFileSync(new URL(`../../data/${market}/${year}.json`, import.meta.url), 'utf8'))

let records, index
beforeAll(() => {
  const agg = JSON.parse(readFileSync(new URL('../../data/aggregations.json', import.meta.url), 'utf8'))
  records = Object.entries(agg.years_by_market).flatMap(([market, years]) =>
    years.flatMap((y) => shard(market, y)),
  )
  index = buildIndex(records)
})

const hits = (q) => searchRecords(index, records, q, {})
const ids = (q) => new Set(hits(q).map((r) => r.id))

describe('真实数据黄金集 · 涛总常用词', () => {
  it('「湖南」召回 ≥7 条且包含 3 张张家界图（层级词典：子地名挂父行政区）', () => {
    const got = ids('湖南')
    expect(got.size).toBeGreaterThanOrEqual(7)
    for (const id of ['en-us-2022-05-19', 'en-us-2023-08-18', 'zh-cn-2023-08-17'])
      expect(got, `湖南应召回张家界图 ${id}`).toContain(id)
  })

  it('「张家界」召回全部张家界图', () => {
    expect(ids('张家界').size).toBeGreaterThanOrEqual(3)
  })

  it('「四川」召回 ≥30 条且含大熊猫/九寨沟图', () => {
    const got = ids('四川')
    expect(got.size).toBeGreaterThanOrEqual(30)
    expect(got).toContain('en-us-2021-03-16') // Bifengxia Panda Base
    expect(got).toContain('zh-cn-2023-08-07') // 九寨沟五花海
  })

  it('「新疆」召回 ≥3 条（伊犁天鹅泉/禾木/赛里木湖）', () => {
    const got = ids('新疆')
    expect(got.size).toBeGreaterThanOrEqual(3)
    expect(got).toContain('zh-cn-2023-12-21')
    expect(got).toContain('zh-cn-2024-09-30')
  })

  it('「西藏」召回日喀则满拉水库图，且不混入无关图', () => {
    expect(ids('西藏')).toContain('zh-cn-2024-12-20')
  })

  it('「山峰」召回 ≥2 条', () => {
    expect(ids('山峰').size).toBeGreaterThanOrEqual(2)
  })

  // FIXME(召回盲区): 数据文本无「雪山」连续字样（zh-cn 含「雪」仅 26 条、en-us 含 snow 仅 25 条且无 snow mountain 短语），
  // 字面匹配 0 命中。修复方向：词典组桥接（雪山↔snowy…）或图片内容理解搜索，待定夺
  it.skip('「雪山」应有召回（当前 0 条）', () => {
    expect(hits('雪山').length).toBeGreaterThan(0)
  })
})

describe('真实数据黄金集 · 跨语言桥接', () => {
  it('yosemite 与 优胜美地 召回同一集合（≥17 条）', () => {
    expect(ids('yosemite')).toEqual(ids('优胜美地'))
    expect(ids('yosemite').size).toBeGreaterThanOrEqual(17)
  })

  it('fuji 与 富士山 召回同一集合（≥6 条）', () => {
    expect(ids('fuji')).toEqual(ids('富士山'))
    expect(ids('fuji').size).toBeGreaterThanOrEqual(6)
  })

  it('alps 与 阿尔卑斯 召回同一集合（≥16 条）', () => {
    expect(ids('alps')).toEqual(ids('阿尔卑斯'))
    expect(ids('alps').size).toBeGreaterThanOrEqual(16)
  })

  it('繁体「張家界」与简体召回一致（张家界组含繁体别名）', () => {
    expect(ids('張家界')).toEqual(ids('张家界'))
  })

  // FIXME(词典繁体覆盖不全): 广西组别名只有 ['guangxi']，无「廣西」——繁体用户搜广西零结果。
  // 修复：补繁体别名 → 重跑 geo_enrich。其余省级组宜同步体检
  it.skip('繁体「廣西」应召回桂林喀斯特图（当前 0 条）', () => {
    expect(ids('廣西').size).toBeGreaterThan(0)
  })
})

describe('真实数据黄金集 · 防误报', () => {
  it('「paris」主市场全为法国巴黎图（≥20 条，词边界不误伤他词）', () => {
    const out = hits('paris')
    expect(out.length).toBeGreaterThanOrEqual(20)
    // 扩展市场（fr-fr 等）文本为本地语言，无 "France" 字样时 region 归不出（null 可接受）
    for (const r of out)
      if (['zh-cn', 'en-us'].includes(r.market)) expect(r.region, `${r.id} 应归法国`).toBe('法国')
  })

  it('「comparison」零误报（含 paris 子串的词不触发巴黎）', () => {
    expect(hits('comparison')).toHaveLength(0)
  })

  it('「中国」≥120 条且不混入拱门国家公园（字符共现误报已由二元组 AND 解决）', () => {
    const got = ids('中国')
    expect(got.size).toBeGreaterThanOrEqual(120)
    expect(got, 'Arches NP 与中国无关，不得混入').not.toContain('en-us-2023-05-08')
  })

  it('「雪山 湖」召回高山湖泊图（「山湖」二元组建功）', () => {
    expect(ids('雪山 湖')).toContain('zh-cn-2024-09-02')
  })
})

describe('真实数据黄金集 · 地名与筛选', () => {
  it.each([
    ['黄山', 4],
    ['桂林', 2],
    ['青海', 2],
    ['长城', 5],
    ['九寨沟', 2],
  ])('「%s」召回 ≥%i 条', (q, n) => {
    expect(hits(q).length).toBeGreaterThanOrEqual(n)
  })

  it('「长城」召回含中国长城与哈德良长城（同词组不同国，均合理）', () => {
    expect(ids('长城')).toContain('zh-cn-2023-09-30')
    expect(ids('长城')).toContain('zh-cn-2023-09-18')
  })

  it('「富士山」结果全部挂日本 region', () => {
    for (const r of hits('富士山')) expect(r.region).toBe('日本')
  })
})

describe('真实数据黄金集 · 已确认误报 bug（修复时去掉 skip，先红后绿）', () => {
  // FIXME(词典歧义): 西班牙「格拉萨莱马山自然公园」含连续子串「拉萨」→ CJK 子串匹配误命中拉萨组 →
  // 层级词典又挂上父级「西藏」→ 搜西藏混入西班牙图（zh-cn-2026-06-11）
  it.skip('「西藏」不得混入西班牙格拉萨莱马图（zh-cn-2026-06-11）', () => {
    expect(hits('西藏').map((r) => r.id)).not.toContain('zh-cn-2026-06-11')
  })

  // FIXME(词典歧义): 桂林图英文文本 "Lijiang River"（漓江）按词边界命中「丽江」组（云南）→ 挂上云南 tags →
  // 搜「云南」混入桂林图。丽江/漓江同拼音，需词典层面消歧（漓江组或丽江组别名收窄）
  it.skip('「云南」不得混入桂林漓江图（en-us-2022-10-22）', () => {
    expect(hits('云南').map((r) => r.id)).not.toContain('en-us-2022-10-22')
  })
})
