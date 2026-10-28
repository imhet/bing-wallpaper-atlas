import { expect, test } from '@playwright/test'

// Service Worker 专用 spec：与 app.spec.js 隔离，避免缓存污染数据类断言。
// 语义模型 23MB 拦掉（SW 测试不关心它），jsDelivr 与缩略图外网隔离同款。
async function stubExternal(page) {
  await page.route('**/th?id=*', (route) =>
    route.fulfill({ status: 200, contentType: 'image/jpeg', body: Buffer.from('') }),
  )
  await page.route('https://cdn.jsdelivr.net/**', (route) => route.fulfill({ status: 503, body: '' }))
  await page.route('**/data/sem/**', (route) => route.abort())
}

test.use({ serviceWorkers: 'allow' })

test('Service Worker：访问过后断网仍可浏览已缓存数据', async ({ page }) => {
  await stubExternal(page)
  await page.goto('/')
  await expect(page.locator('.card').first()).toBeVisible({ timeout: 15000 })
  await page.evaluate(() => navigator.serviceWorker.ready)
  // SW 控制下的这次加载把数据分片写进缓存
  await page.reload()
  await expect(page.locator('.card').first()).toBeVisible({ timeout: 15000 })
  await page.context().setOffline(true)
  await page.reload()
  await expect(page.locator('.card').first()).toBeVisible({ timeout: 15000 })
  await expect(page.locator('.result-count')).toContainText('共')
})
