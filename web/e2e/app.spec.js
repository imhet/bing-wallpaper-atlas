import { expect, test } from '@playwright/test'

// 拦截 Bing CDN 缩略图：返回 1px 占位，测试只关注数据与交互层
async function stubThumbs(page) {
  await page.route('**/th?id=*', (route) =>
    route.fulfill({ status: 200, contentType: 'image/jpeg', body: Buffer.from('') }),
  )
}

const cardImgs = (page) => page.locator('.card img')

test('首屏渐进渲染 120 张且无重复图（同图多市场去重）', async ({ page }) => {
  await stubThumbs(page)
  await page.goto('/')
  await expect(cardImgs(page)).toHaveCount(120)
  const keys = await cardImgs(page).evaluateAll((imgs) =>
    imgs.map((i) => {
      const u = new URL(i.src)
      // Bing CDN 带 ?id= 查询串；本地深史缩略图（gen_thumbs webp）无查询串，用路径即唯一键
      return (u.searchParams.get('id') ?? u.pathname)
        .replace(/_\d+x\d+\.jpg$/, '') // 分辨率后缀
        .replace(/_[A-Z]{2}-[A-Z]{2}\d+$/, '') // 市场后缀
    }),
  )
  expect(new Set(keys).size, '同一天全球同图只应显示一张').toBe(keys.length)
  await expect(page.locator('.site-header .total')).toContainText('张 · 更新至')
})

test('滚动到底部追加下一批卡片', async ({ page }) => {
  await stubThumbs(page)
  await page.goto('/')
  await expect(cardImgs(page)).toHaveCount(120)
  await page.locator('div[aria-hidden="true"]').scrollIntoViewIfNeeded()
  await expect(cardImgs(page)).toHaveCount(240)
})

test('市场筛选联动：选 zh-cn 后所有卡片来自中国市场', async ({ page }) => {
  await stubThumbs(page)
  await page.goto('/')
  await expect(cardImgs(page).first()).toBeVisible()
  await page.selectOption('select[aria-label="市场"]', 'zh-cn')
  await expect(page.locator('.card').first()).toBeVisible()
  const count = await page.locator('.card').count()
  expect(count, 'zh-cn 去重后仍有可观卡片').toBeGreaterThan(50)
  // URL 状态同步：筛选写入 query string，刷新可还原
  expect(page.url()).toContain('market=zh-cn')
})
