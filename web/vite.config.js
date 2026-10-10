import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

export default defineConfig({
  base: './',
  plugins: [vue()],
  // e2e/ 是 Playwright 用例，交给 `npx playwright test`，vitest 不扫
  test: { exclude: ['**/node_modules/**', 'e2e/**'] },
})
