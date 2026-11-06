import assert from 'node:assert/strict'
import test from 'node:test'
import worker from './index.js'

// 代理转发一律打桩，测试不联网
const stubFetch = () => {
  globalThis.fetch = async () => new Response('ok', { status: 200 })
}

test('www 下的壁纸路径 301 到裸域（www 整站被博客兜底，不截住就回博客首页）', async () => {
  stubFetch()
  const resp = await worker.fetch(new Request('https://www.heyitao.com/wallpaper/'))
  assert.equal(resp.status, 301)
  assert.equal(resp.headers.get('location'), 'https://heyitao.com/wallpaper/', '必须带到裸域，不是 www')
})

test('www 无尾斜杠：补斜杠并归一裸域，查询串保留', async () => {
  stubFetch()
  const resp = await worker.fetch(new Request('https://www.heyitao.com/wallpaper?pic=zh-cn-2026-11-05'))
  assert.equal(resp.status, 301)
  assert.equal(resp.headers.get('location'), 'https://heyitao.com/wallpaper/?pic=zh-cn-2026-11-05')
})

test('www 下的深层壁纸路径同样 301 到裸域', async () => {
  stubFetch()
  const resp = await worker.fetch(new Request('https://www.heyitao.com/wallpaper/data/aggregations.json'))
  assert.equal(resp.status, 301)
  assert.equal(resp.headers.get('location'), 'https://heyitao.com/wallpaper/data/aggregations.json')
})

test('裸域无尾斜杠补斜杠，不跳到 www', async () => {
  stubFetch()
  const resp = await worker.fetch(new Request('https://heyitao.com/wallpaper'))
  assert.equal(resp.status, 301)
  assert.equal(resp.headers.get('location'), 'https://heyitao.com/wallpaper/')
})

test('裸域壁纸路径正常代理到 Pages', async () => {
  let seen
  globalThis.fetch = async (req) => {
    seen = req.url
    return new Response('ok', { status: 200 })
  }
  const resp = await worker.fetch(new Request('https://heyitao.com/wallpaper/data/a.json'))
  assert.equal(resp.status, 200)
  assert.equal(seen, 'https://bing-wallpaper-atlas-5n6.pages.dev/data/a.json')
})
