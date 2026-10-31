import { describe, expect, it } from 'vitest'
import { MESSAGES, REGION_EN, format, imageCount, pickLang } from './i18n'

describe('pickLang', () => {
  it('已保存的语言优先于浏览器语言', () => {
    expect(pickLang('en', 'zh-CN')).toBe('en')
    expect(pickLang('zh', 'en-US')).toBe('zh')
  })

  it('中文浏览器（含繁体）默认中文', () => {
    expect(pickLang(null, 'zh-CN')).toBe('zh')
    expect(pickLang(null, 'zh-TW')).toBe('zh')
    expect(pickLang(null, 'zh')).toBe('zh')
  })

  it('非中文浏览器默认英文', () => {
    expect(pickLang(null, 'en-US')).toBe('en')
    expect(pickLang(null, 'ja-JP')).toBe('en')
    expect(pickLang(null, 'de-DE')).toBe('en')
  })

  it('浏览器语言缺失时默认英文', () => {
    expect(pickLang(null, '')).toBe('en')
    expect(pickLang(null, undefined)).toBe('en')
  })

  it('存储里的非法值被忽略（回落到浏览器判断）', () => {
    expect(pickLang('fr', 'zh-CN')).toBe('zh')
    expect(pickLang('', 'en-US')).toBe('en')
  })
})

describe('文案表', () => {
  it('中英文 key 完全一致（缺一条就是界面残留中文/英文）', () => {
    expect(Object.keys(MESSAGES.en).sort()).toEqual(Object.keys(MESSAGES.zh).sort())
  })

  it('没有任何空文案', () => {
    for (const lang of ['zh', 'en'])
      for (const [k, v] of Object.entries(MESSAGES[lang])) expect(v.trim(), `${lang}.${k}`).not.toBe('')
  })
})

describe('format', () => {
  it('替换模板变量', () => {
    expect(format('找到 {n} 张', { n: 3 })).toBe('找到 3 张')
    expect(format('{a} 和 {b}', { a: 'x', b: 'y' })).toBe('x 和 y')
  })

  it('缺变量时原样保留占位符（便于发现漏传）', () => {
    expect(format('找到 {n} 张', {})).toBe('找到 {n} 张')
  })
})

describe('imageCount', () => {
  it('中文带量词，英文区分单复数', () => {
    expect(imageCount('zh', 1)).toBe('1 张')
    expect(imageCount('zh', 2)).toBe('2 张')
    expect(imageCount('en', 1)).toBe('1 image')
    expect(imageCount('en', 2)).toBe('2 images')
  })
})

describe('REGION_EN', () => {
  it('覆盖数据中出现的全部 77 个地区值', () => {
    // 数据侧的 region 规范名是中文；少一个英文模式就会露出中文
    expect(Object.keys(REGION_EN)).toHaveLength(77)
  })

  it('抽查易错的几个', () => {
    expect(REGION_EN['美国']).toBe('United States')
    expect(REGION_EN['英国']).toBe('United Kingdom')
    expect(REGION_EN['韩国']).toBe('South Korea')
    expect(REGION_EN['缅甸']).toBe('Myanmar')
    expect(REGION_EN['中国']).toBe('China')
  })
})
