import { describe, expect, it } from 'vitest'
import { needsRefresh, shouldProbe, REFRESH_MIN_INTERVAL_MS } from './refresh'

const HOUR = 3600 * 1000

describe('shouldProbe：标签页重新可见时要不要花 474B 探一次', () => {
  it('距上次加载不足 6 小时不探（切来切去不产生请求）', () => {
    expect(shouldProbe(1000, 1000 + 5 * HOUR)).toBe(false)
  })

  it('刚到 6 小时就探', () => {
    expect(shouldProbe(1000, 1000 + REFRESH_MIN_INTERVAL_MS)).toBe(true)
  })

  it('从未记录过加载时间（首屏还没完成）不探', () => {
    expect(shouldProbe(0, Date.now())).toBe(false)
  })
})

describe('needsRefresh：探针结果决定要不要重拉全量', () => {
  it('latest_date 变了要重拉', () => {
    expect(needsRefresh('2026-11-04', '2026-11-05')).toBe(true)
  })

  it('latest_date 没变不重拉', () => {
    expect(needsRefresh('2026-11-05', '2026-11-05')).toBe(false)
  })

  it('探针失败（空响应）保持现状，不能把页面数据清掉', () => {
    expect(needsRefresh('2026-11-05', null)).toBe(false)
    expect(needsRefresh('2026-11-05', undefined)).toBe(false)
  })

  it('原先没有记录过日期时，只要探到日期就重拉', () => {
    expect(needsRefresh(null, '2026-11-05')).toBe(true)
  })
})
