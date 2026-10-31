import { expect, test } from '@playwright/test'

// 与 search.spec.js 同款外网隔离：缩略图占位、jsDelivr 按不可达处理，数据只走本地 Pages
async function stubThumbs(page) {
  await page.route('**/th?id=*', (route) =>
    route.fulfill({ status: 200, contentType: 'image/jpeg', body: Buffer.from('') }),
  )
  await page.route('https://cdn.jsdelivr.net/**', (route) => route.fulfill({ status: 503, body: '' }))
  await page.route('**/data/sem/**', (route) => route.abort())
}

test.describe('英文浏览器（en-US）直接进入英文界面', () => {
  test.use({ locale: 'en-US' })

  test('界面骨架是英文：lang/title/搜索框/结果计数', async ({ page }) => {
    await stubThumbs(page)
    await page.goto('/')
    await expect(page.locator('html')).toHaveAttribute('lang', 'en')
    await expect(page.locator('h1')).toHaveText('Bing Wallpaper Atlas')
    await expect(page.locator('input.query')).toHaveAttribute('placeholder', /Search titles/)
    await expect(page.locator('.result-count')).toContainText('images', { timeout: 20000 })
  })

  test('卡片标题用英文版本（同图组 en-us 当代表）', async ({ page }) => {
    await stubThumbs(page)
    await page.goto('/')
    await expect(page.locator('.card').first()).toBeVisible({ timeout: 20000 })
    const titles = await page
      .locator('.card .title')
      .evaluateAll((els) => els.slice(0, 10).map((e) => e.textContent.trim()))
    const ascii = titles.filter((t) => !/[一-鿿]/.test(t)).length
    // 同一天全球同图，en-us 记录标题是英文；允许少量图无英文版本
    expect(ascii).toBeGreaterThanOrEqual(8)
  })
})

test.describe('手动语言切换（默认中文环境）', () => {
  test('点切换按钮变英文，刷新后保持，再点回中文', async ({ page }) => {
    await stubThumbs(page)
    await page.goto('/')
    await expect(page.locator('h1')).toHaveText('Bing 壁纸图集')

    await page.locator('.lang-toggle').click()
    await expect(page.locator('h1')).toHaveText('Bing Wallpaper Atlas')
    await expect(page.locator('html')).toHaveAttribute('lang', 'en')
    await expect(page.locator('input.query')).toHaveAttribute('placeholder', /Search titles/)

    await page.reload()
    await expect(page.locator('h1')).toHaveText('Bing Wallpaper Atlas')

    await page.locator('.lang-toggle').click()
    await expect(page.locator('h1')).toHaveText('Bing 壁纸图集')
    await expect(page.locator('html')).toHaveAttribute('lang', 'zh-CN')
  })
})
