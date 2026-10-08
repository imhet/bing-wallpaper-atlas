import { describe, expect, it } from 'vitest'
import { suggestFromDict } from './suggest'

const DICT = { 京都: ['kyoto', 'きょうと', '京都府'], 瑞士: ['switzerland', 'schweiz'] }

describe('suggestFromDict', () => {
  it('suggests other writings of the same place', () => {
    expect(suggestFromDict('kyoto', DICT)).toEqual(['京都', 'きょうと', '京都府'])
    expect(suggestFromDict('京都', DICT)).toEqual(['kyoto', 'きょうと', '京都府'])
  })
  it('is case-insensitive and trims', () => {
    expect(suggestFromDict('  SWITZERLAND ', DICT)).toEqual(['瑞士', 'schweiz'])
  })
  it('returns empty for unknown or empty queries', () => {
    expect(suggestFromDict('xyz', DICT)).toEqual([])
    expect(suggestFromDict('', DICT)).toEqual([])
  })
})
