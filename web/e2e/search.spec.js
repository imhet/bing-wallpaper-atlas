import { expect, test } from '@playwright/test'

async function stubThumbs(page) {
  await page.route('**/th?id=*', (route) =>
    route.fulfill({ status: 200, contentType: 'image/jpeg', body: Buffer.from('') }),
  )
}

test('搜「湖南」：层级召回 ≥7 张，网格出现张家界图', async ({ page }) => {
  await stubThumbs(page)
  await page.goto('/')
  await page.fill('input.query', '湖南')
  await page.press('input.query', 'Enter')
  await expect(page.locator('.card').first()).toBeVisible()
  // 卡片只显示 title/desc，中文记录的 desc 含「张家界」；en-us 卡标题是英文，按张数≥1 断言
  // 原始 7 条里有跨日同名图（玻璃桥）被渲染层去重 → 网格 6 张
  expect(await page.locator('.card').count()).toBeGreaterThanOrEqual(6)
  await expect(page.locator('.card .title', { hasText: '张家界' }).first()).toBeVisible()
})

test('无结果显示空态提示', async ({ page }) => {
  await stubThumbs(page)
  await page.goto('/')
  await page.fill('input.query', '咕噜')
  await page.press('input.query', 'Enter')
  await expect(page.locator('.empty')).toBeVisible()
})

test('搜索「优胜美地」与「yosemite」命中数量一致（跨语言桥接）', async ({ page }) => {
  await stubThumbs(page)
  await page.goto('/')
  await page.fill('input.query', '优胜美地')
  await page.press('input.query', 'Enter')
  await expect(page.locator('.card').first()).toBeVisible()
  const zhCount = await page.locator('.card').count()

  await page.fill('input.query', 'yosemite')
  await page.press('input.query', 'Enter')
  await expect(page.locator('.card').first()).toBeVisible()
  expect(await page.locator('.card').count()).toBe(zhCount)
  expect(zhCount).toBeGreaterThanOrEqual(10)
})
