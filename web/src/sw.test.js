import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

// public/sw.js 是独立脚本（不能 import），在最小 SW 环境里执行它、抓 fetch 监听器来断言路由。
// location.href 即 SW 脚本自身地址，等价于部署根：/sw.js → '/'，/wallpaper/sw.js → '/wallpaper/'。
const SRC = readFileSync(new URL('../public/sw.js', import.meta.url), 'utf8')
const ORIGIN = 'https://example.com'

function loadSW(scriptPath = '/sw.js') {
  const listeners = {}
  const fetched = []
  const cache = { match: async () => undefined, put: async () => {}, addAll: async () => {} }
  const self = {
    addEventListener: (type, fn) => (listeners[type] = fn),
    skipWaiting: () => {},
    clients: { claim: () => {} },
  }
  const caches = { open: async () => cache, keys: async () => [], delete: async () => true }
  const fetchStub = async (req) => {
    fetched.push(new URL(typeof req === 'string' ? req : req.url).pathname)
    return { ok: true, clone() { return this } }
  }
  const location = { href: `${ORIGIN}${scriptPath}`, origin: ORIGIN }
  new Function('self', 'location', 'caches', 'fetch', SRC)(self, location, caches, fetchStub)
  return { listeners, fetched }
}

// 触发 fetch 事件；返回 respondWith 的 promise（undefined 表示 SW 不接管该请求）
function dispatch(listeners, pathname, mode = 'cors') {
  let responded
  listeners.fetch({
    request: { method: 'GET', url: `${ORIGIN}${pathname}`, mode },
    respondWith: (p) => (responded = p),
  })
  return responded
}

describe('Service Worker 在子路径部署下的路由（heyitao.com/wallpaper/）', () => {
  it('根路径部署：数据分片走 stale-while-revalidate', async () => {
    const { listeners, fetched } = loadSW('/sw.js')
    const p = dispatch(listeners, '/data/zh-cn/2026.json')
    expect(p, '根部署下数据必须被接管').toBeTruthy()
    await p
    expect(fetched).toEqual(['/data/zh-cn/2026.json'])
  })

  it('子路径部署：数据分片同样走 stale-while-revalidate', async () => {
    const { listeners, fetched } = loadSW('/wallpaper/sw.js')
    const p = dispatch(listeners, '/wallpaper/data/zh-cn/2026.json')
    expect(p, '子路径下数据仍须被接管，否则日更缓存整层失效').toBeTruthy()
    await p
    expect(fetched).toEqual(['/wallpaper/data/zh-cn/2026.json'])
  })

  it('子路径部署：模型文件仍 cache-first', async () => {
    const { listeners } = loadSW('/wallpaper/sw.js')
    expect(dispatch(listeners, '/wallpaper/data/sem/bge/model_4bit.onnx')).toBeTruthy()
  })

  it('子路径部署：页面导航仍 network-first', async () => {
    const { listeners } = loadSW('/wallpaper/sw.js')
    expect(dispatch(listeners, '/wallpaper/', 'navigate')).toBeTruthy()
  })

  it('跨域请求一律不接管', async () => {
    const { listeners } = loadSW('/wallpaper/sw.js')
    const event = {
      request: { method: 'GET', url: 'https://cdn.jsdelivr.net/gh/x/data.json', mode: 'cors' },
      respondWith: () => {
        throw new Error('不该接管跨域请求')
      },
    }
    listeners.fetch(event)
  })
})
