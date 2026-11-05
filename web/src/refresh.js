// 标签页长期开着时数据会停在打开那天（应用只在打开时拉一次）。重新可见时先探一次
// aggregations.json（474B，内含 latest_date），只有日期真的变了才重拉全量——
// 无脑重拉是每次 3.6MB，切来切去受不了。

export const REFRESH_MIN_INTERVAL_MS = 6 * 60 * 60 * 1000

// 距上次加载够久才值得探。lastLoadedAt 为 0 表示首屏还没加载完，不插队。
export function shouldProbe(lastLoadedAt, now, intervalMs = REFRESH_MIN_INTERVAL_MS) {
  if (!lastLoadedAt) return false
  return now - lastLoadedAt >= intervalMs
}

// 探针结果决定要不要重拉：探针失败（空响应）必须保持现状，不能把页面已有数据清掉。
export function needsRefresh(prevLatestDate, nextLatestDate) {
  if (!nextLatestDate) return false
  return nextLatestDate !== prevLatestDate
}
