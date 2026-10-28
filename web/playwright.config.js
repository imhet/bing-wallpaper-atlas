import { defineConfig } from '@playwright/test'

// E2E 跑 vite preview（默认 4173；已有实例则复用）。缩略图直链 Bing CDN，
// 测试里统一拦截成占位响应——只验证数据/交互层，不依赖第三方 CDN 的可用性。
export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  retries: 0,
  use: {
    baseURL: 'http://localhost:4173',
    channel: 'chrome', // 系统 Chrome，免下载浏览器
    headless: true,
    // SW 发起的 fetch 不走 page.route——开着会让所有用例的 mock 失效。
    // SW 行为只在 sw.spec.js 里用 test.use 单独开启
    serviceWorkers: 'block',
  },
  webServer: {
    command: 'npm run preview -- --port 4173 --strictPort',
    port: 4173,
    reuseExistingServer: !process.env.CI,
  },
})
