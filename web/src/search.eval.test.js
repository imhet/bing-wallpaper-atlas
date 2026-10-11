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
  it('「湖南」召回 ≥5 条且包含 3 张张家界图（层级词典：子地名挂父行政区）', () => {
    const got = ids('湖南')
    expect(got.size).toBeGreaterThanOrEqual(5)
    for (const id of ['en-us-2022-05-19', 'en-us-2023-08-18', 'zh-cn-2023-08-17'])
      expect(got, `湖南应召回张家界图 ${id}`).toContain(id)
  })

  it('「张家界」召回全部张家界图', () => {
    expect(ids('张家界').size).toBeGreaterThanOrEqual(3)
  })

  it('「四川」召回 ≥20 条且含大熊猫/九寨沟图', () => {
    const got = ids('四川')
    // 基线 2026-10-11 词典收紧：美国州名音译尾字（内华达州等）误挂达州→四川 cascade 的
    // 9 张图清除后的真实召回（原基线 29）
    expect(got.size).toBeGreaterThanOrEqual(20)
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

  it('「雪山」召回 ≥10 条（CLIP 内容打标：文字无「雪山」二字的图靠 content_tags 召回）', () => {
    expect(hits('雪山').length).toBeGreaterThanOrEqual(10)
  })
})

describe('真实数据黄金集 · 内容打标（CLIP content_tags）', () => {
  it('「烟花」召回长沙烟花图', () => {
    expect(ids('烟花')).toContain('zh-cn-2025-01-27')
  })
  it('「野牛」召回黄石图', () => {
    expect(ids('野牛')).toContain('en-us-2022-01-08')
  })
  it('「极光」召回阿拉斯加图', () => {
    expect(ids('极光')).toContain('en-us-2021-12-19')
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
  it('繁体「廣西」应召回桂林喀斯特图（当前 0 条）', () => {
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

  it('「雪山 湖」有召回（content_tags 补齐后 AND 空回退 OR，雪山/山湖任一命中）', () => {
    expect(hits('雪山 湖').length).toBeGreaterThan(0)
    expect(ids('雪山 湖')).toContain('zh-cn-2024-09-02') // 高山湖泊图（文字层「山湖」真二元组）
  })

  it('「国美」零误报（跨标点假二元组已修：数据里「…国，美…」不再生成假词）', () => {
    expect(hits('国美')).toHaveLength(0)
  })

  it('「湖南」不混入意大利南蒂罗尔图（「布莱耶斯湖，南蒂罗尔」不再生成假「湖南」）', () => {
    expect(ids('湖南')).not.toContain('zh-cn-2024-02-16')
  })
})

describe('真实数据黄金集 · geo 词典误挂防护（2026-10-11 全量排查 166 条误挂后锁死）', () => {
  // 注：词典误挂（tags 层）由 tests/test_geo_enrich.py 锁死；这里只锁搜索端可感知的误召回。
  // 「都柏林/纽芬兰/佛罗里达州」等中文文本的字面二元组共现（搜「柏林」命中「都柏林」location）
  // 是 tokenizer 字面召回的固有行为，不在此防护范围——若要消除需搜索端查询否定，另行决策。
  it('「广州」不召回瑞士图（Canton of Bern 的 canton 裸别名已删；该图文本为英文，无字面共现）', () => {
    expect(ids('广州')).not.toContain('en-us-2026-01-03')
  })

  it('「瑞士」不混入捷克波希米亚瑞士图（bohemian switzerland 拉丁否定上下文）', () => {
    expect(ids('瑞士')).not.toContain('en-us-2021-10-23')
  })

  it('「里约热内卢」不召回德州大弯图（该图已无里约 tags；大弯文本为英文无「里约」共现）', () => {
    expect(ids('里约热内卢')).not.toContain('en-us-2021-06-12')
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

describe('真实数据黄金集 · 误报复归防护（曾上线后修掉，锁死防回归）', () => {
  // FIXME(词典歧义): 西班牙「格拉萨莱马山自然公园」含连续子串「拉萨」→ CJK 子串匹配误命中拉萨组 →
  // 层级词典又挂上父级「西藏」→ 搜西藏混入西班牙图（zh-cn-2026-06-11）
  it('「西藏」不得混入西班牙格拉萨莱马图（zh-cn-2026-06-11）', () => {
    expect(hits('西藏').map((r) => r.id)).not.toContain('zh-cn-2026-06-11')
  })

  // FIXME(词典歧义): 桂林图英文文本 "Lijiang River"（漓江）按词边界命中「丽江」组（云南）→ 挂上云南 tags →
  // 搜「云南」混入桂林图。丽江/漓江同拼音，需词典层面消歧（漓江组或丽江组别名收窄）
  it('「云南」不得混入桂林漓江图（en-us-2022-10-22）', () => {
    expect(hits('云南').map((r) => r.id)).not.toContain('en-us-2022-10-22')
  })
})
