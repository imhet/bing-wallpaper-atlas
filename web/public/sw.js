/* Service Worker：二次访问提速 + 断网兜底。
 *
 * 缓存策略按「文件会不会变」分三档：
 * - 哈希 assets / 模型（data/sem/bge，人工版本管理不变）/ 图标：cache-first
 * - 数据分片与语义向量（每日更新会重写）：stale-while-revalidate——缓存秒开 + 后台拉新，
 *   滞后窗口与 jsDelivr purge 窗口同量级（最多一次更新周期），下一次刷新即对齐
 * - 页面导航：network-first，失败回壳缓存（离线 reload 不落浏览器错误页）
 * 其余请求（sw.js 自身、跨域）不拦截。
 */

const VERSION = 'v1'
const SHELL = `shell-${VERSION}`
const RUNTIME = `runtime-${VERSION}`

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(SHELL)
      .then((cache) => cache.addAll(['./', './index.html']))
      .then(() => self.skipWaiting()),
  )
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== SHELL && k !== RUNTIME).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  )
})

const CACHE_FIRST = [
  (url) => url.pathname.includes('/assets/'), // vite 哈希文件名，内容不可变
  (url) => url.pathname.includes('/data/sem/bge/'), // 模型/vocab/wasm：版本号进路径才更新
  (url) => /\.(png|svg|ico|webp)$/.test(url.pathname), // 图标类
]

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url)
  if (event.request.method !== 'GET' || url.origin !== location.origin) return
  if (CACHE_FIRST.some((test) => test(url))) {
    event.respondWith(cacheFirst(event.request))
  } else if (url.pathname.startsWith('/data/')) {
    event.respondWith(staleWhileRevalidate(event.request))
  } else if (event.request.mode === 'navigate') {
    event.respondWith(networkFirst(event.request))
  }
})

async function cacheFirst(request) {
  const cache = await caches.open(RUNTIME)
  const hit = await cache.match(request)
  if (hit) return hit
  const resp = await fetch(request)
  if (resp.ok) cache.put(request, resp.clone())
  return resp
}

async function staleWhileRevalidate(request) {
  const cache = await caches.open(RUNTIME)
  const hit = await cache.match(request)
  const network = fetch(request)
    .then((resp) => {
      if (resp.ok) cache.put(request, resp.clone())
      return resp
    })
    .catch(() => null)
  return hit || (await network) || new Response('{"error":"offline"}', { status: 503, headers: { 'Content-Type': 'application/json' } })
}

async function networkFirst(request) {
  const cache = await caches.open(SHELL)
  try {
    const resp = await fetch(request)
    if (resp.ok) cache.put(request, resp.clone())
    return resp
  } catch {
    return (await cache.match('./index.html')) || Response.error()
  }
}
