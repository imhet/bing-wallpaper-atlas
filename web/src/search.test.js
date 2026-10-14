import { describe, expect, it } from 'vitest'
import { buildIndex, highlightParts, parseDateQuery, searchRecords, tokenize } from './search'

const records = [
  { id: 'zh-cn-2023-10-05', market: 'zh-cn', date: '2023-10-05', title: '云海仙境',
    desc: '张家界雪山云海 (© Li Hua/Getty Images)', location: ['张家界国家森林公园'], region: '中国',
    photographer: 'Li Hua', gallery: 'Getty Images', tags: [], resolutions: { uhd: true, thumb: true } },
  { id: 'en-us-2024-01-01', market: 'en-us', date: '2024-01-01', title: 'Winter Alps',
    desc: 'Snowy Alps (© John Doe)', location: ['Snowy Alps'], region: '瑞士',
    photographer: 'John Doe', gallery: null, tags: [], resolutions: { uhd: false, thumb: true } },
  { id: 'zh-cn-2024-05-01', market: 'zh-cn', date: '2024-05-01', title: '北窗框景',
    desc: '拱门国家公园的北窗框景中的炮塔拱门, 犹他州, 美国 (© John Doe)',
    location: ['拱门国家公园'], region: '美国',
    photographer: 'John Doe', gallery: null, tags: [], resolutions: { uhd: false, thumb: true } },
  { id: 'ja-jp-2024-03-01', market: 'ja-jp', date: '2024-03-01', title: '桜と塔',
    desc: '東京の春 (© Yuki Sato)', location: ['東京タワー'], region: '日本',
    photographer: 'Yuki Sato', gallery: null,
    tags: ['东京', 'tokyo', '東京', 'とうきょう'], resolutions: { uhd: false, thumb: true } },
]

const index = buildIndex(records)

describe('tokenize', () => {
  it('splits CJK into single chars plus bigrams', () => {
    // 单字负责模糊回退，二元组负责词语精确匹配（「中国」不能再靠 中+国 字符共现命中）
    expect(tokenize('中国雪山')).toEqual(['中', '中国', '国', '国雪', '雪', '雪山', '山'])
  })
  it('splits kana like CJK (tags bridge to katakana aliases)', () => {
    // 片假名曾是盲区（被 tokenizer 丢弃 → 查询变空）；现与汉字同等待遇
    expect(tokenize('アルプス')).toEqual(['ア', 'アル', 'ル', 'ルプ', 'プ', 'プス', 'ス'])
  })

describe('highlightParts', () => {
  const DICT = { 京都: ['kyoto', 'きょうと', '京都府'], 阿尔卑斯: ['alps'] }
  it('marks matched CJK and latin spans', () => {
    expect(highlightParts('阿尔卑斯山脉的安德马特', '阿尔卑斯', DICT)).toEqual([
      { text: '阿尔卑斯', hit: true },
      { text: '山脉的安德马特', hit: false },
    ])
    // 词典桥接：中文查询高亮英文文本里的对应地名
    expect(highlightParts('Autumn in Kyoto', '京都', DICT)).toEqual([
      { text: 'Autumn in ', hit: false },
      { text: 'Kyoto', hit: true },
    ])
  })
  it('returns the whole text unmarked without a usable query', () => {
    expect(highlightParts('Anything', '')).toEqual([{ text: 'Anything', hit: false }])
    expect(highlightParts('Anything', '((')).toEqual([{ text: 'Anything', hit: false }])
  })
})
  it('keeps latin words whole and lowercases', () => {
    expect(tokenize('Alaska 2024')).toEqual(['alaska', '2024'])
  })
  it('does not form bigrams across punctuation or spaces', () => {
    // 跨标点假相邻曾生成假词「湖南」（「布莱耶斯湖，南蒂罗尔」），导致搜湖南混入意大利图
    expect(tokenize('布莱耶斯湖，南蒂罗尔')).not.toContain('湖南')
    expect(tokenize('湖，南')).toEqual(['湖', '南'])
    expect(tokenize('雪山 湖')).toEqual(['雪', '雪山', '山', '湖'])
  })
})

describe('searchRecords', () => {
  it('matches the word 中国 but not mere char cooccurrence', () => {
    // 「拱门国家公园…框景中…美国」含「中」「国」两个单字但不含「中国」一词，必须排除
    const hits = searchRecords(index, records, '中国', {})
    expect(hits.map((r) => r.id)).toEqual(['zh-cn-2023-10-05'])
  })

  it('AND-matches contiguous CJK compound in one field', () => {
    // 「国家森林」要求连续词组：zh-cn 的 location「张家界国家森林公园」命中，其余排除
    const hits = searchRecords(index, records, '国家森林', {})
    expect(hits.map((r) => r.id)).toEqual(['zh-cn-2023-10-05'])
  })

  it('AND-matches Chinese compound query', () => {
    const hits = searchRecords(index, records, '中国雪山', {})
    expect(hits.map((r) => r.id)).toEqual(['zh-cn-2023-10-05'])
  })

  it('searches by photographer', () => {
    const hits = searchRecords(index, records, 'Li Hua', {})
    expect(hits.map((r) => r.id)).toEqual(['zh-cn-2023-10-05'])
  })

  it('falls back to OR when AND finds nothing', () => {
    // '瑞士张家界'：连续串无分隔 → 单段，段内 AND 空 → OR 回退应命中两条
    const hits = searchRecords(index, records, '瑞士张家界', {})
    expect(hits.map((r) => r.id).sort()).toEqual(['en-us-2024-01-01', 'zh-cn-2023-10-05'])
  })

  it('multi-keyword: 的/空格切段，段间 AND（「中国 的 雪山」只命中同时含两词的记录）', () => {
    const hits = searchRecords(index, records, '中国 的 雪山', {})
    expect(hits.map((r) => r.id)).toEqual(['zh-cn-2023-10-05'])
  })

  it('multi-keyword: 无记录同时满足各段 → 交集为空（不再 OR 并集噪声）', () => {
    // 带分隔的多词是 AND 语义：瑞士与张家界无同图 → 0 条
    expect(searchRecords(index, records, '瑞士 的 张家界', {})).toHaveLength(0)
  })

  it('cross-language: 中文 tags 命中英文查询，英文 tags 命中中文查询', () => {
    // 词典方案的核心闭环：ja-jp 日文记录靠 tags 被中文/英文查询命中
    expect(searchRecords(index, records, '东京', {}).map((r) => r.id)).toEqual(['ja-jp-2024-03-01'])
    expect(searchRecords(index, records, 'tokyo', {}).map((r) => r.id)).toEqual(['ja-jp-2024-03-01'])
  })

  it('filters by market/year/resolution', () => {
    expect(searchRecords(index, records, '', { market: 'en-us' })).toHaveLength(1)
    expect(searchRecords(index, records, '', { year: 2023 })).toHaveLength(1)
    expect(searchRecords(index, records, '', { resolution: 'uhd' }).map((r) => r.id))
      .toEqual(['zh-cn-2023-10-05'])
    expect(searchRecords(index, records, '', { month: 1 })).toHaveLength(1)
  })
})

describe('parseDateQuery（日期搜索）', () => {
  it('8 位 / 带分隔日期 → 精确当天', () => {
    const m = parseDateQuery('2026-10-01')
    expect(m({ date: '2026-10-01' })).toBe(true)
    expect(m({ date: '2025-10-01' })).toBe(false)
    expect(parseDateQuery('20261001')({ date: '2026-10-01' })).toBe(true)
    expect(parseDateQuery('2026.10.01')({ date: '2026-10-01' })).toBe(true)
  })

  it('MM-DD / MMDD → 每一年的这一天', () => {
    const m = parseDateQuery('10-01')
    expect(m({ date: '2023-10-01' })).toBe(true)
    expect(m({ date: '2026-10-01' })).toBe(true)
    expect(m({ date: '2026-10-02' })).toBe(false)
    expect(parseDateQuery('1001')({ date: '2015-10-01' })).toBe(true)
  })

  it('非法月日回退年份语义；非数字返回 null 走全文检索', () => {
    expect(parseDateQuery('2026')({ date: '2026-05-05' })).toBe(true)
    expect(parseDateQuery('2026')({ date: '2025-05-05' })).toBe(false)
    expect(parseDateQuery('20261301')).toBe(null) // 13 月非法 → 不当日期
    expect(parseDateQuery('abc')).toBe(null)
  })

  it('searchRecords 集成：日期查询精确命中，混入筛选仍生效', () => {
    expect(searchRecords(index, records, '2023-10-05', {}).map((r) => r.id)).toEqual(['zh-cn-2023-10-05'])
    expect(searchRecords(index, records, '0101', {}).map((r) => r.id)).toEqual(['en-us-2024-01-01'])
    expect(searchRecords(index, records, '2023-10-05', { market: 'en-us' })).toHaveLength(0)
  })
})
