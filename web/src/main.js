import { createApp } from 'vue'
import App from './App.vue'
import './styles.css'

createApp(App).mount('#app')

// Service Worker：二次访问提速 + 断网兜底（策略见 public/sw.js）。注册失败静默——
// 无 SW 的站点功能完整，只是少了这两样
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => navigator.serviceWorker.register('./sw.js').catch(() => {}))
}
