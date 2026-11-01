import { describe, expect, it, vi } from 'vitest'
import { createWakeLock } from './wakeLock'

// 浏览器替身：只实现本模块用到的 wakeLock.request
const fakeNav = (requestImpl) => ({ wakeLock: { request: requestImpl } })

describe('createWakeLock', () => {
  it('进入时申请屏幕常亮', async () => {
    const request = vi.fn().mockResolvedValue({ release: vi.fn() })
    const lock = createWakeLock(fakeNav(request))
    expect(await lock.acquire()).toBe(true)
    expect(request).toHaveBeenCalledWith('screen')
  })

  it('浏览器不支持时不抛错、退回 false', async () => {
    const lock = createWakeLock({})
    expect(await lock.acquire()).toBe(false)
  })

  it('被策略/可见性拒绝时不抛错（不影响观看）', async () => {
    const lock = createWakeLock(fakeNav(vi.fn().mockRejectedValue(new Error('NotAllowedError'))))
    expect(await lock.acquire()).toBe(false)
  })

  it('退出时释放已持有的锁', async () => {
    const release = vi.fn().mockResolvedValue(undefined)
    const lock = createWakeLock(fakeNav(vi.fn().mockResolvedValue({ release })))
    await lock.acquire()
    await lock.release()
    expect(release).toHaveBeenCalled()
  })

  it('释放后再次申请会重新请求（标签页切回场景）', async () => {
    const request = vi.fn().mockResolvedValue({ release: vi.fn() })
    const lock = createWakeLock(fakeNav(request))
    await lock.acquire()
    await lock.release()
    await lock.acquire()
    expect(request).toHaveBeenCalledTimes(2)
  })

  it('没有申请过就释放是安全的空操作', async () => {
    const lock = createWakeLock(fakeNav(vi.fn()))
    await expect(lock.release()).resolves.toBeUndefined()
  })
})
