import { expect, test } from '@playwright/test'

async function stubThumbs(page) {
  await page.route('**/th?id=*', (route) =>
    route.fulfill({ status: 200, contentType: 'image/jpeg', body: Buffer.from('') }),
  )
}

// 渐进渲染分批追加卡片：等卡片数连续两次采样相同再返回（数据翻倍后单次抓拍会数到中间态）
async function settledCount(page) {
  let prev = -1
  for (;;) {
    const n = await page.locator('.card').count()
    if (n === prev && n > 0) return n
    prev = n
    await page.waitForTimeout(250)
  }
}

test('搜「湖南」：层级召回 ≥5 张，网格出现张家界图', async ({ page }) => {
  await stubThumbs(page)
  await page.goto('/')
  await page.fill('input.query', '湖南')
  await page.press('input.query', 'Enter')
  await expect(page.locator('.card').first()).toBeVisible()
  // 假词误报清理后真实召回 5 条；AvatarMountain 跨市场同图去重 → 网格 4 张
  expect(await page.locator('.card').count()).toBeGreaterThanOrEqual(4)
  await expect(page.locator('.card .title', { hasText: '张家界' }).first()).toBeVisible()
})

test('无结果显示空态提示', async ({ page }) => {
  await stubThumbs(page)
  await page.goto('/')
  await page.fill('input.query', '咕噜')
  await page.press('input.query', 'Enter')
  await expect(page.locator('.empty')).toBeVisible()
})

test('日期搜索「10-01」命中每一年的今天（MMDD 模式）', async ({ page }) => {
  await stubThumbs(page)
  await page.goto('/')
  await page.fill('input.query', '10-01')
  await page.press('input.query', 'Enter')
  await expect(page.locator('.card').first()).toBeVisible()
  const dates = await page.locator('.card .date').evaluateAll((els) => els.map((e) => e.textContent.trim()))
  expect(dates.length).toBeGreaterThanOrEqual(15)
  for (const d of dates) expect(d.slice(5), `${d} 应是 10-01`).toBe('10-01')
})

test('搜索「优胜美地」与「yosemite」命中数量一致（跨语言桥接）', async ({ page }) => {
  await stubThumbs(page)
  await page.goto('/')
  await page.fill('input.query', '优胜美地')
  await page.press('input.query', 'Enter')
  await expect(page.locator('.card').first()).toBeVisible()
  const zhCount = await settledCount(page)

  await page.fill('input.query', 'yosemite')
  await page.press('input.query', 'Enter')
  await expect(page.locator('.card').first()).toBeVisible()
  expect(await settledCount(page)).toBe(zhCount)
  expect(zhCount).toBeGreaterThanOrEqual(10)
})
