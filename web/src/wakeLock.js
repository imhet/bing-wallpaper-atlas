// Screen Wake Lock：沉浸观赏是长时间盯着不动的使用方式，系统闲置计时会锁屏/熄屏打断观看。
// 用 W3C Screen Wake Lock 保持屏幕常亮，不支持/被策略拒绝时静默降级（观看不受影响）。
// 注意浏览器会在页面隐藏时自动释放锁——切回标签页必须重新申请，否则锁名存实亡。
export function createWakeLock(nav = globalThis.navigator) {
  let sentinel = null
  async function acquire() {
    if (!nav?.wakeLock?.request || sentinel) return !!sentinel
    try {
      sentinel = await nav.wakeLock.request('screen')
      return true
    } catch {
      // NotAllowedError（被策略/权限拒绝）或 SecurityError（非安全上下文）：静默降级
      return false
    }
  }
  async function release() {
    const s = sentinel
    sentinel = null
    if (!s) return
    try {
      await s.release() // 重复 release 会 reject，吞掉即可
    } catch {
      /* 已释放 */
    }
  }
  return { acquire, release }
}
