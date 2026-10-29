import { expect, test } from '@playwright/test'
import fs from 'node:fs'

// 外网隔离：Bing CDN 缩略图返回占位、jsDelivr 数据分流按不可达处理（fetchJSON 自动回退
// Pages 相对路径）——测试只关注本地数据与交互层，不依赖第三方可用性
async function stubExternal(page) {
  await page.route('**/th?id=*', (route) =>
    route.fulfill({ status: 200, contentType: 'image/jpeg', body: Buffer.from('') }),
  )
  await page.route('https://cdn.jsdelivr.net/**', (route) => route.fulfill({ status: 503, body: '' }))
}

const cardImgs = (page) => page.locator('.card img')

// 等全量分片到齐：渐进窗口内 records 重排会让列表起点漂移 1~2 张（分级加载的已知行为），
// 沉浸类用例的列表位置断言必须在全量口径下进行
async function waitFullData(page) {
  await expect(page.locator('.result-count')).not.toContainText('加载中', { timeout: 15000 })
}

test('首屏渐进渲染 120 张且无重复图（同图多市场去重）', async ({ page }) => {
  await stubExternal(page)
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
  await expect(page.locator('.site-header .total-link')).toContainText('更新日志')
})

test('首屏分级：主视角市场先渲染，其余市场分片延迟不阻塞首屏', async ({ page }) => {
  await stubExternal(page)
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
  await stubExternal(page)
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

test('数据请求走 jsDelivr 分流且页面正常渲染（CDN 可达路径）', async ({ page }) => {
  await page.route('**/th?id=*', (route) =>
    route.fulfill({ status: 200, contentType: 'image/jpeg', body: Buffer.from('') }),
  )
  const cdnCalls = []
  // 放行 jsDelivr：数据内容仍取本地 server 的同一份文件——断言点是「请求走了 CDN 域名」
  await page.route('https://cdn.jsdelivr.net/**', async (route) => {
    const path = new URL(route.request().url()).pathname.replace(/^\/gh\/imhet\/bing-wallpaper-atlas@main/, '')
    cdnCalls.push(path)
    await route.fulfill({ response: await page.request.get(path) })
  })
  await page.goto('/')
  await waitFullData(page)
  await expect(cardImgs(page).first()).toBeVisible()
  expect(cdnCalls).toContain('/data/aggregations.json')
  expect(cdnCalls.some((p) => /^\/data\/zh-cn\/\d{4}\.json$/.test(p)), '分片也应走 CDN').toBe(true)
})

test('分享链接 ?pic= 直达详情弹层，关闭后参数移除', async ({ page }) => {
  await stubExternal(page)
  const zh = await (await page.request.get('/data/zh-cn/2026.json')).json()
  const rec = zh.find((r) => r.title || r.desc)
  await page.goto(`/?pic=${rec.id}`)
  // id 自含市场+年份：单分片快速通道直接开弹层（不等全量；全量兜底仍在）
  await expect(page.locator('.modal h2')).toBeVisible({ timeout: 15000 })
  await expect(page.locator('.modal h2')).toHaveText(rec.title || rec.desc)
  await expect(page.locator('.modal .facts dd').first()).toContainText(rec.market)
  await page.locator('.modal .close').click()
  await expect(page.locator('.modal')).toHaveCount(0)
  expect(new URL(page.url()).searchParams.get('pic')).toBeNull()
})

test('分享链接 ?pic=：单分片快速开弹层，不等全量', async ({ page }) => {
  await stubExternal(page)
  // 只放行启动必需的聚合文件 + 一级窗口两个年分片，其余 data 请求全部掐断：
  // 全量永远到不了（loadAllRecords 必失败），弹层还能打开才算快速通道生效。
  // fixtures 用 page.request 预取（API 请求不走 page.route，不会被掐）
  const fixtures = {}
  for (const f of ['aggregations.json', 'zh-cn/2026.json', 'en-us/2026.json'])
    fixtures[f] = await (await page.request.get(`/data/${f}`)).body()
  await page.route('**/data/**', (route) => route.abort())
  for (const [f, body] of Object.entries(fixtures))
    await page.route(`**/data/${f}`, (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body }),
    )
  const zh = await (await page.request.get('/data/zh-cn/2026.json')).json()
  const rec = zh[zh.length - 1]
  await page.goto(`/?pic=${rec.id}`)
  await expect(page.locator('.modal h2')).toBeVisible({ timeout: 5000 })
  await expect(page.locator('.modal h2')).toHaveText(rec.title || rec.desc)
})

test('收藏导入：上传导出格式 JSON 后收藏恢复', async ({ page }) => {
  await stubExternal(page)
  const doc = {
    app: 'bing-wallpaper-atlas',
    version: 1,
    favorites: {
      'test-import-key': {
        id: 'zh-cn-2026-01-01', date: '2026-01-01', market: 'zh-cn',
        urlbase: '/th?id=OHR.ImportTest_ZH-CN1', favAt: Date.now(),
        title: '导入测试图', desc: '', location: [], region: '', photographer: '',
        gallery: '', copyrightlink: '', tags: [], content_tags: [], resolutions: {},
      },
    },
  }
  await page.goto('/')
  await page.click('.site-header button:has-text("收藏")')
  await page.setInputFiles('input[type=file]', {
    name: 'favs.json',
    mimeType: 'application/json',
    buffer: Buffer.from(JSON.stringify(doc)),
  })
  await expect(page.locator('.import-msg')).toContainText('已导入 1 张')
  await expect(page.locator('.card .title', { hasText: '导入测试图' }).first()).toBeVisible()
})

test('收藏导出：下载的 JSON 是可再导入的 v1 格式', async ({ page }) => {
  await stubExternal(page)
  await page.goto('/')
  await expect(page.locator('.card').first()).toBeVisible()
  await page.locator('.card .fav').first().dispatchEvent('click') // hover 才显现，dispatchEvent 绕过
  await page.click('.site-header button:has-text("收藏")')
  await expect(page.locator('.card').first()).toBeVisible()
  const [download] = await Promise.all([page.waitForEvent('download'), page.click('button:has-text("导出收藏")')])
  const doc = JSON.parse(await fs.promises.readFile(await download.path(), 'utf8'))
  expect(doc.app).toBe('bing-wallpaper-atlas')
  expect(doc.version).toBe(1)
  expect(Object.keys(doc.favorites)).toHaveLength(1)
})

test('详情弹层展示同图的其他市场版本并可切换', async ({ page }) => {
  await stubExternal(page)
  await page.goto('/')
  await page.fill('input.query', '2024-04-02')
  await expect(page.locator('.card').first()).toBeVisible({ timeout: 15000 }) // 全量分片到货后才命中
  await page.locator('.card').first().click()
  await expect(page.locator('.modal h2')).toBeVisible()
  const versions = page.locator('.siblings > button') // 直接子级：排除相似图网格里的按钮
  // JutlandSpring 同图有 en-us/de-de/en-gb/fr-fr 四个市场版本，当前 en-us → 另外 3 个
  await expect(versions).toHaveCount(3)
  await versions.filter({ hasText: 'Deutsch' }).click()
  await expect(page.locator('.modal .facts dd').first()).toContainText('de-de')
})

test('详情弹层展示相似的图并可点击切换（图向量就绪后）', async ({ page }) => {
  await stubExternal(page)
  await page.goto('/')
  // 相似索引在全量数据 + 空闲回调后建（只拉图向量分片），给足就绪时间
  await page.fill('input.query', '2024-04-02')
  await expect(page.locator('.card').first()).toBeVisible({ timeout: 15000 })
  await page.locator('.card').first().click()
  await expect(page.locator('.modal h2')).toBeVisible()
  const grid = page.locator('.similar-grid button')
  await expect(grid.first()).toBeVisible({ timeout: 20000 })
  const before = await page.locator('.modal h2').textContent()
  await grid.first().click()
  // 相似卡片走 select-sibling 通道：弹层切换到该组代表记录，标题随之变化
  await expect(page.locator('.modal h2')).not.toHaveText(before)
  await expect(page.locator('.modal .similar-grid')).toBeVisible()
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
  await page.route('https://cdn.jsdelivr.net/**', (route) => route.fulfill({ status: 503, body: '' }))
  await page.goto('/')
  await expect(page.locator('.card .thumb .skeleton').first()).toBeVisible()
  await expect(page.locator('.card .thumb').first()).toHaveClass(/loaded/, { timeout: 6000 })
  await expect(page.locator('.card .thumb').first().locator('.skeleton')).toHaveCount(0)
})

test('缩略图加载失败显示兜底占位', async ({ page }) => {
  await page.route('**/th?id=*', (route) => route.fulfill({ status: 404, contentType: 'image/jpeg', body: Buffer.from('') }))
  await page.route('https://cdn.jsdelivr.net/**', (route) => route.fulfill({ status: 503, body: '' }))
  await page.goto('/')
  await expect(page.locator('.card .thumb-fallback').first()).toBeVisible()
})

test('全量数据加载中：零结果提示「数据仍在加载」而非「没有匹配」', async ({ page }) => {
  await stubExternal(page)
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

test('分享元信息：og 图存在，描述不含过期计数', async ({ page }) => {
  await page.goto('/')
  const desc = await page.getAttribute('meta[property="og:description"]', 'content')
  expect(desc).not.toMatch(/\d{3,}\+/) // 曾硬编码「3446+ 张」
  await expect(page.locator('meta[property="og:image"]')).toHaveAttribute(
    'content',
    'https://imhet.github.io/bing-wallpaper-atlas/og.png',
  )
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute(
    'href',
    'https://imhet.github.io/bing-wallpaper-atlas/',
  )
  const resp = await page.request.get('/og.png')
  expect(resp.ok()).toBe(true)
  expect((await resp.body()).length).toBeGreaterThan(10000)
})

test('首屏数据未到时不显示「没有匹配的壁纸」', async ({ page }) => {
  await stubExternal(page)
  await page.route('**/data/*/*.json', async (route) => {
    await new Promise((r) => setTimeout(r, 2000))
    await route.continue()
  })
  await page.goto('/')
  await expect(page.locator('.status')).toHaveText('加载中…')
  // 即时断言（toHaveCount(0) 会自动等待，2 秒后数据到货就会误判通过）
  expect(await page.locator('.empty').count()).toBe(0)
  await page.unrouteAll({ behavior: 'ignoreErrors' })
})

test('详情：默认 1080p，切换市场版本后标签与档位同步', async ({ page }) => {
  await stubExternal(page)
  await page.goto('/')
  await page.fill('input.query', '2024-04-06')
  await expect(page.locator('.card').first()).toBeVisible({ timeout: 15000 }) // 全量分片到货后才命中
  await page.locator('.card').first().click()
  const hero = page.locator('.modal .hero')
  // 默认 1080p：此前 available[0] 是 uhd，每开一张详情都拉几 MB 的 4K 原图
  await expect(hero).toHaveAttribute('src', /_1920x1080\.jpg/)
  const tags = page.locator('.modal .tag-row').first().locator('button')
  await expect(tags).toHaveCount(3) // en-us JapanHimeji：姬路/姫路/日本
  await page.locator('.res-switch button', { hasText: '4K UHD' }).click()
  await expect(hero).toHaveAttribute('src', /_UHD\.jpg/)
  await page.locator('.siblings button', { hasText: 'Français' }).click()
  await expect(page.locator('.modal .facts dd').first()).toContainText('fr-fr')
  // 标签是 setup 时常量时切市场不更新，仍显示 en-us 的 3 个
  await expect(tags).toHaveCount(2) // fr-fr：姬路/姫路
  // 镜像记录只有原图一档；picked 未重置会继续拼 4K 后缀。
  // 档位行单档也显示（与深史旧图的详情格式统一），但内容必须是「原图」
  await expect(hero).toHaveAttribute('src', 'https://bing.npanuhin.me/FR/fr/2024-04-06.jpg')
  const switchBtns = page.locator('.res-switch button')
  await expect(switchBtns).toHaveCount(1)
  await expect(switchBtns).toHaveText('原图')
  await expect(switchBtns).toHaveClass(/active/)
})

test('详情弹层：焦点进入并归还，背景滚动锁定', async ({ page }) => {
  await stubExternal(page)
  await page.goto('/')
  await expect(page.locator('.card').first()).toBeVisible()
  const card = page.locator('.card').first()
  await card.click()
  const modal = page.locator('.modal')
  await expect(modal).toBeVisible()
  expect(await modal.evaluate((el) => el.contains(document.activeElement))).toBe(true)
  expect(await page.evaluate(() => getComputedStyle(document.body).overflow)).toBe('hidden')
  await page.keyboard.press('Escape')
  await expect(modal).toHaveCount(0)
  // 数据补齐可能替换掉原卡片节点，断言焦点回到网格（而不是掉到 body）
  expect(await page.evaluate(() => document.querySelector('.grid')?.contains(document.activeElement))).toBe(true)
  expect(await page.evaluate(() => getComputedStyle(document.body).overflow)).not.toBe('hidden')
})

test('结果计数：无筛选显示总数，搜索后显示命中张数', async ({ page }) => {
  await stubExternal(page)
  await page.goto('/')
  const count = page.locator('.result-count')
  // 等全量数据到货（首屏一级只有最新年，总数需背景补齐）
  await expect(count).toHaveText(/^共 [1-9]\d{3,} 张$/, { timeout: 20000 })
  await page.fill('input.query', '2025-11-04')
  await expect(page.locator('.card')).toHaveCount(2)
  await expect(count).toHaveText('找到 2 张')
})

test('筛选面板：按钮打开底部面板，面板内搜索并选中摄影师', async ({ page }) => {
  await stubExternal(page)
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
  await stubExternal(page)
  await page.goto('/?photographer=Nick+Brundle+Photography')
  const count = page.locator('.result-count')
  await expect(count).toHaveText(/^找到 \d+ 张$/, { timeout: 20000 })
  await expect(page.locator('.filter-bar .filter-btn', { hasText: 'Nick Brundle Photography' })).toBeVisible()
  // 计数与网格卡片数同口径；结果 < 120 不触发渐进切片，数量稳定
  const n = await page.locator('.card').count()
  await expect(count).toHaveText(`找到 ${n} 张`)
})

test('选中值被其他筛选筛空时，面板仍保留该项并显示 0', async ({ page }) => {
  await stubExternal(page)
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
  await stubExternal(page)
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
  await stubExternal(page)
  await page.goto('/')
  await expect(cardImgs(page)).toHaveCount(120)
  await page.locator('div[aria-hidden="true"]').scrollIntoViewIfNeeded()
  await expect(cardImgs(page)).toHaveCount(240)
})

test('市场筛选联动：选 zh-cn 后所有卡片来自中国市场', async ({ page }) => {
  await stubExternal(page)
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

test('更新日志：按日期倒序分组，点卡片进详情，URL 可直达', async ({ page }) => {
  await stubExternal(page)
  await page.goto('/?view=updates')
  await expect(page.locator('.day-group').first()).toBeVisible({ timeout: 15000 })
  const dates = await page.locator('.day-group h3').evaluateAll((els) => els.map((e) => e.textContent.trim().slice(0, 10)))
  expect(dates.length).toBeGreaterThan(1)
  expect([...dates].sort().reverse()).toEqual(dates) // 倒序
  // 组内市场徽标（同一天多市场不去重，正是「哪天哪个市场更新了什么」）
  await expect(page.locator('.day-group').first().locator('.market-badge').first()).toBeVisible()
  // 点卡片进详情弹层
  await page.locator('.day-group .card').first().click()
  await expect(page.locator('.modal h2')).toBeVisible()
  // 站头入口可返回浏览视图
  await page.getByRole('button', { name: '关闭' }).click()
  await page.getByRole('button', { name: '← 返回浏览' }).first().click()
  await expect(page.locator('.filter-bar')).toBeVisible()
})

test('沉浸模式：弹层进入，键盘切换与到头禁用，Esc 只退沉浸不关弹层', async ({ page }) => {
  await stubExternal(page)
  await page.goto('/')
  await waitFullData(page)
  await page.locator('.card').first().click()
  await expect(page.locator('.modal h2')).toBeVisible()
  await page.getByRole('button', { name: '沉浸观赏' }).click()
  const viewer = page.locator('.viewer')
  await expect(viewer).toBeVisible()
  await expect(viewer.locator('.viewer-img')).toBeVisible()
  const count = viewer.locator('.viewer-count')
  await expect(count).toContainText('1 / ')
  // → 下一张、← 上一张、到头 ← 无效
  await page.keyboard.press('ArrowRight')
  await expect(count).toContainText('2 / ')
  await page.keyboard.press('ArrowLeft')
  await expect(count).toContainText('1 / ')
  await page.keyboard.press('ArrowLeft')
  await expect(count).toContainText('1 / ')
  // Esc 只退沉浸，详情弹层还在
  await page.keyboard.press('Escape')
  await expect(viewer).toHaveCount(0)
  await expect(page.locator('.modal h2')).toBeVisible()
})

test('沉浸模式：浏览器吞掉 Esc 只退全屏时，跟随退出直回详情弹层', async ({ page }) => {
  await stubExternal(page)
  await page.goto('/')
  await waitFullData(page)
  await page.locator('.card').first().click()
  await expect(page.locator('.modal h2')).toBeVisible()
  await page.getByRole('button', { name: '沉浸观赏' }).click()
  const viewer = page.locator('.viewer')
  await expect(viewer).toBeVisible()
  // 真实浏览器里全屏态的第一次 Esc 被 browser 保留（退出全屏，页面收不到 keydown）：
  // 用 exitFullscreen 模拟这次退出，沉浸应连带关闭，直接回到详情弹层而不是停在中间态
  await page.evaluate(() => document.exitFullscreen?.())
  await expect(viewer).toHaveCount(0)
  await expect(page.locator('.modal h2')).toBeVisible()
})

test('沉浸模式：鼠标移动显示信息，空闲 3 秒后自动隐藏（含光标）', async ({ page }) => {
  await page.clock.install()
  await stubExternal(page)
  await page.goto('/')
  await page.locator('.card').first().click()
  await page.getByRole('button', { name: '沉浸观赏' }).click()
  await expect(page.locator('.viewer')).toBeVisible()
  await page.mouse.move(400, 300) // 移动鼠标 → 信息浮现
  await expect(page.locator('.viewer .viewer-meta')).toBeVisible()
  await page.clock.fastForward(3500) // 空闲 → idle 态（信息与光标 opacity 淡出，Playwright 可见性判定不认 opacity，断言 class）
  await expect(page.locator('.viewer.viewer-idle')).toHaveCount(1)
})

test('沉浸模式：左右拖拽（触摸滑动）切换上一张/下一张', async ({ page }) => {
  await stubExternal(page)
  await page.goto('/')
  await waitFullData(page)
  await page.locator('.card').first().click()
  await page.getByRole('button', { name: '沉浸观赏' }).click()
  const count = page.locator('.viewer-count')
  await expect(count).toContainText('1 / ')
  await page.mouse.move(700, 400)
  await page.mouse.down()
  await page.mouse.move(200, 400, { steps: 5 }) // 向左拖 = 下一张
  await page.mouse.up()
  await expect(count).toContainText('2 / ')
  await page.mouse.move(200, 400)
  await page.mouse.down()
  await page.mouse.move(700, 400, { steps: 5 }) // 向右拖 = 上一张
  await page.mouse.up()
  await expect(count).toContainText('1 / ')
})

test('沉浸模式：双击图片收藏，↑ 收藏 ↓ 取消，心形按钮实时同步', async ({ page }) => {
  await stubExternal(page)
  await page.goto('/')
  await waitFullData(page)
  await page.locator('.card').first().click()
  await page.locator('.modal-top .immerse-btn').click()
  const favBtn = page.locator('.viewer .viewer-fav')
  await expect(favBtn).toBeVisible()
  await page.locator('.viewer-img').dblclick() // 双击收藏
  await expect(favBtn).toHaveClass(/on/)
  await expect(page.locator('.heart-burst')).toHaveCount(1) // 画面反馈：心形飘起
  await expect(page.locator('.site-header')).toContainText('收藏 1')
  await page.keyboard.press('ArrowDown') // ↓ 取消收藏
  await expect(favBtn).not.toHaveClass(/on/)
  await page.keyboard.press('ArrowUp') // ↑ 再收藏
  await expect(favBtn).toHaveClass(/on/)
  await expect(page.locator('.site-header')).toContainText('收藏 1')
  await page.waitForTimeout(1200) // 动画结束后移除
  await expect(page.locator('.heart-burst')).toHaveCount(0)
  // 顶排两按钮不得重叠（曾经被残留的 absolute 定位拽出 flex 流叠在一起）
  const favBox = await page.locator('.viewer-fav').boundingBox()
  const closeBox = await page.locator('.viewer-close').boundingBox()
  expect(favBox.x + favBox.width, '收藏按钮右缘应落在关闭按钮左缘之左').toBeLessThanOrEqual(closeBox.x)
})

test('沉浸模式：未预加载的慢图切换显示 spinner，已就绪的图立即切换不闪黑', async ({ page }) => {
  const pixel = Buffer.from(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==',
    'base64',
  )
  // 第二张图（下一张预加载目标）延迟 1.5 秒：预加载 promise 还没回来，走 spinner 路径
  await page.route('**/th?id=*', async (route) => {
    const url = route.request().url()
    if (/_1920x1080/.test(url) && !url.includes('OHR.X_zh-cn1_400')) {
      await new Promise((r) => setTimeout(r, 1500))
    }
    await route.fulfill({ status: 200, contentType: 'image/png', body: pixel })
  })
  await page.goto('/')
  await page.locator('.card').first().click()
  await page.locator('.modal-top .immerse-btn').click()
  // 首张图在弹层阶段已被浏览器预热（同 URL），spinner 一闪而过测不到；第二张的预加载被延迟 1.5s，
  // 按 → 时必然未就绪 → 走 spinner 路径
  await page.keyboard.press('ArrowRight')
  await expect(page.locator('.viewer-spinner')).toBeVisible()
  await expect(page.locator('.viewer-spinner')).toHaveCount(0, { timeout: 5000 })
})

test('沉浸模式：进入时显示操作提示，约 2.5 秒后消失', async ({ page }) => {
  await page.clock.install()
  await stubExternal(page)
  await page.goto('/')
  await waitFullData(page)
  await page.locator('.card').first().click()
  await page.locator('.modal-top .immerse-btn').click()
  const hint = page.locator('.viewer-hint')
  await expect(hint).toBeVisible()
  await expect(hint).toContainText('Esc 退出')
  await page.clock.fastForward(3000)
  await expect(hint).toHaveCount(0)
})

test('更新日志：下滑后出现返回顶部按钮，点击平滑回顶', async ({ page }) => {
  await stubExternal(page)
  await page.goto('/?view=updates')
  await expect(page.locator('.day-group').first()).toBeVisible({ timeout: 15000 })
  const topBtn = page.locator('.back-top')
  await expect(topBtn).toBeHidden()
  await page.mouse.wheel(0, 3000)
  await expect(topBtn).toBeVisible()
  await topBtn.click()
  await expect.poll(() => page.evaluate(() => window.scrollY), { timeout: 5000 }).toBe(0)
  await expect(topBtn).toBeHidden()
})

test('首页卡片日期严格倒序（同图跨市场去重后按本体日重排）', async ({ page }) => {
  await stubExternal(page)
  await page.goto('/')
  await expect(page.locator('.card').first()).toBeVisible({ timeout: 15000 })
  // 等全量到齐：渐进窗口内 records 重排会造成瞬时逆序假象
  await expect(page.locator('.result-count')).not.toContainText('加载中', { timeout: 15000 })
  const dates = await page
    .locator('.card .date')
    .evaluateAll((els) => els.map((e) => e.textContent.trim().slice(0, 10)))
  expect(dates.length).toBeGreaterThan(50)
  const bad = []
  for (let i = 1; i < dates.length; i++) if (dates[i] > dates[i - 1]) bad.push(`${dates[i - 1]}→${dates[i]}@${i}`)
  expect(bad, `日期逆序点: ${bad.slice(0, 5).join(', ')}`).toHaveLength(0)
})
