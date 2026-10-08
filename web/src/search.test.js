import { describe, expect, it } from 'vitest'
import { buildIndex, highlightParts, searchRecords, tokenize } from './search'

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
    // '瑞士张家界'：没有任何记录同时含这两组词 → AND 空 → OR 回退应命中两条
    const hits = searchRecords(index, records, '瑞士张家界', {})
    expect(hits.map((r) => r.id).sort()).toEqual(['en-us-2024-01-01', 'zh-cn-2023-10-05'])
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
