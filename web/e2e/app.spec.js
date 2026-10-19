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

test('首屏分级：主视角市场先渲染，其余市场分片延迟不阻塞首屏', async ({ page }) => {
  await stubThumbs(page)
  // 四市场 2026 分片延迟 3 秒——首屏只等 zh-cn/en-us（慢链路首屏批 3.3MB 是首页慢主因）。
  // 延迟响应给固定空 body：用例只关心首屏出图不等数据内容；route.fetch 在 test 结束后会炸（Test ended）
  for (const m of ['ja-jp', 'de-de', 'fr-fr', 'en-gb'])
    await page.route(`**/data/${m}/2026.json`, async (route) => {
      await new Promise((r) => setTimeout(r, 3000))
      await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
    })
  await page.goto('/')
  await expect(cardImgs(page).first()).toBeVisible({ timeout: 2500 })
  await page.unrouteAll({ behavior: 'ignoreErrors' }) // 清掉还在 3 秒延迟中的回调，不泄漏给同 worker 下个用例
})

test('首屏首张卡即最新日期（一级分片必须倒序渲染，不能等全量到货才纠正）', async ({ page }) => {
  await stubThumbs(page)
  // 非一级分片直接阻断：断言只针对「一级渲染窗口」，避免全量到货后的重渲染竞态
  await page.route('**/data/*/*.json', async (route) => {
    if (/\/(zh-cn|en-us)\/2026\.json$/.test(route.request().url())) await route.continue()
    else await route.abort()
  })
  await page.goto('/')
  await expect(page.locator('.card').first()).toBeVisible()
  // 断言一级渲染窗口内首张卡已是最新月份（此前分片文件正序 → 首屏先出现 1 月）。
  // 不比较具体日期：同图跨市场发布日不同，去重代表记录的日期可能比分组首条早一天
  const us = await (await page.request.get('/data/en-us/2026.json')).json()
  const zh = await (await page.request.get('/data/zh-cn/2026.json')).json()
  const latestMonth = [...us, ...zh].map((r) => r.date.slice(0, 7)).sort().at(-1)
  const firstDate = await page.locator('.card .date').first().textContent()
  expect(firstDate.trim().slice(0, 7)).toBe(latestMonth)
  await page.unrouteAll({ behavior: 'ignoreErrors' })
})

test('详情弹层展示同图的其他市场版本并可切换', async ({ page }) => {
  await stubThumbs(page)
  await page.goto('/')
  await page.fill('input.query', '2024-04-02')
  await expect(page.locator('.card').first()).toBeVisible()
  await page.locator('.card').first().click()
  await expect(page.locator('.modal h2')).toBeVisible()
  const versions = page.locator('.siblings button')
  // JutlandSpring 同图有 en-us/de-de/en-gb/fr-fr 四个市场版本，当前 en-us → 另外 3 个
  await expect(versions).toHaveCount(3)
  await versions.filter({ hasText: 'Deutsch' }).click()
  await expect(page.locator('.modal .facts dd').first()).toContainText('de-de')
})

test('缩略图加载中显示骨架占位，加载完成后淡入', async ({ page }) => {
  // 1×1 透明 PNG：空 body 会被浏览器判为解码失败（error），触发不了 load
  const pixel = Buffer.from(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==',
    'base64',
  )
  await page.route('**/th?id=*', async (route) => {
    await new Promise((r) => setTimeout(r, 1200))
    await route.fulfill({ status: 200, contentType: 'image/png', body: pixel })
  })
  await page.goto('/')
  await expect(page.locator('.card .thumb .skeleton').first()).toBeVisible()
  await expect(page.locator('.card .thumb').first()).toHaveClass(/loaded/, { timeout: 6000 })
  await expect(page.locator('.card .thumb').first().locator('.skeleton')).toHaveCount(0)
})

test('缩略图加载失败显示兜底占位', async ({ page }) => {
  await page.route('**/th?id=*', (route) => route.fulfill({ status: 404, contentType: 'image/jpeg', body: Buffer.from('') }))
  await page.goto('/')
  await expect(page.locator('.card .thumb-fallback').first()).toBeVisible()
})

test('全量数据加载中：零结果提示「数据仍在加载」而非「没有匹配」', async ({ page }) => {
  await stubThumbs(page)
  // 非一级分片延迟 8 秒：模拟慢链路全量补齐期间搜索（西藏记录在 zh-cn/2024，尚未到货）
  await page.route('**/data/*/*.json', async (route) => {
    if (!/\/(zh-cn|en-us)\/2026\.json$/.test(route.request().url()))
      await new Promise((r) => setTimeout(r, 8000))
    await route.continue()
  })
  await page.goto('/')
  await expect(cardImgs(page).first()).toBeVisible()
  await page.fill('input.query', '西藏')
  await expect(page.locator('.empty')).toHaveText('数据仍在加载，请稍候…')
  await page.unrouteAll({ behavior: 'ignoreErrors' })
})

test('结果计数：无筛选显示总数，搜索后显示命中张数', async ({ page }) => {
  await stubThumbs(page)
  await page.goto('/')
  const count = page.locator('.result-count')
  // 等全量数据到货（首屏一级只有最新年，总数需背景补齐）
  await expect(count).toHaveText(/^共 [1-9]\d{3,} 张$/, { timeout: 20000 })
  await page.fill('input.query', '2025-11-04')
  await expect(page.locator('.card')).toHaveCount(2)
  await expect(count).toHaveText('找到 2 张')
})

test('筛选面板：按钮打开底部面板，面板内搜索并选中摄影师', async ({ page }) => {
  await stubThumbs(page)
  await page.goto('/')
  await expect(page.locator('.card').first()).toBeVisible()
  // 原生下拉全部换成按钮 + 面板（摄影师取值 4000+、最长 147 字符，原生下拉撑爆宽度）
  await expect(page.locator('.filter-bar select')).toHaveCount(0)

  await page.getByRole('button', { name: /全部摄影师/ }).click()
  const sheet = page.locator('.filter-sheet')
  await expect(sheet).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(sheet).toBeHidden()

  await page.getByRole('button', { name: /全部摄影师/ }).click()
  await page.fill('.filter-sheet .sheet-search', 'Brundle')
  await expect(sheet.locator('.option-name', { hasText: 'Nick Brundle Photography' })).toBeVisible()
  await expect(sheet.locator('.option-name', { hasText: 'NASA' })).toHaveCount(0) // 已按关键字过滤
  await sheet.locator('.option', { hasText: 'Nick Brundle Photography' }).click()
  await expect(sheet).toBeHidden()
  // 卡片标题里也含摄影师名，用筛选按钮限定
  await expect(page.locator('.filter-bar .filter-btn', { hasText: 'Nick Brundle Photography' })).toBeVisible()
  await expect(page.locator('.result-count')).toHaveText(/^找到 \d+ 张$/)
  expect(new URL(page.url()).searchParams.get('photographer')).toBe('Nick Brundle Photography')
})

test('URL 直达带摄影师筛选：按钮文案与结果计数正确还原', async ({ page }) => {
  await stubThumbs(page)
  await page.goto('/?photographer=Nick+Brundle+Photography')
  const count = page.locator('.result-count')
  await expect(count).toHaveText(/^找到 \d+ 张$/, { timeout: 20000 })
  await expect(page.locator('.filter-bar .filter-btn', { hasText: 'Nick Brundle Photography' })).toBeVisible()
  // 计数与网格卡片数同口径；结果 < 120 不触发渐进切片，数量稳定
  const n = await page.locator('.card').count()
  await expect(count).toHaveText(`找到 ${n} 张`)
})

test('选中值被其他筛选筛空时，面板仍保留该项并显示 0', async ({ page }) => {
  await stubThumbs(page)
  // 分面口径下 UI 选不出 0 结果组合，真实场景是分享链接直达：
  // George Steinmetz 仅出现在 en-us，与 zh-cn 组合为空
  await page.goto('/?photographer=George+Steinmetz&market=zh-cn')
  await expect(page.locator('.result-count')).toHaveText(/^找到 0 张$/, { timeout: 20000 })
  // 面板里选中项不能消失（否则用户无法看到当前值、也无法改回）
  await page.getByRole('button', { name: /George Steinmetz/ }).click()
  await page.fill('.filter-sheet .sheet-search', 'George Steinmetz')
  const option = page.locator('.filter-sheet .option', { hasText: 'George Steinmetz' })
  await expect(option).toBeVisible()
  await expect(option).toHaveClass(/active/)
  await expect(option.locator('.option-count')).toHaveText('0')
})

test('筛选面板：焦点进入面板并在关闭后归还，打开时锁定背景滚动', async ({ page }) => {
  await stubThumbs(page)
  await page.goto('/')
  const trigger = page.getByRole('button', { name: /全部摄影师/ })
  await trigger.click()
  const sheet = page.locator('.filter-sheet')
  await expect(sheet).toBeVisible()
  // 焦点必须进入面板（键盘/读屏用户否则仍在背后的按钮上）
  expect(await sheet.evaluate((el) => el.contains(document.activeElement))).toBe(true)
  // 面板打开时背景不可滚动
  expect(await page.evaluate(() => getComputedStyle(document.body).overflow)).toBe('hidden')
  await page.keyboard.press('Escape')
  await expect(sheet).toBeHidden()
  expect(await trigger.evaluate((el) => el === document.activeElement)).toBe(true)
  expect(await page.evaluate(() => getComputedStyle(document.body).overflow)).not.toBe('hidden')
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
  await page.getByRole('button', { name: /全部市场/ }).click()
  await page.locator('.filter-sheet .option', { hasText: 'zh-cn' }).click()
  await expect(page.locator('.card').first()).toBeVisible()
  const count = await page.locator('.card').count()
  expect(count, 'zh-cn 去重后仍有可观卡片').toBeGreaterThan(50)
  // URL 状态同步：筛选写入 query string，刷新可还原
  expect(page.url()).toContain('market=zh-cn')
})
