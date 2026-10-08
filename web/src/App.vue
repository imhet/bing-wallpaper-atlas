<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { loadAggregations, loadAllRecords, loadYearShards } from './api'
import { buildIndex, searchRecords } from './search'
import { encodeFilters, decodeFilters } from './urlState'
import { suggestFromDict } from './suggest'
import FilterBar from './components/FilterBar.vue'
import WallpaperGrid from './components/WallpaperGrid.vue'
import WallpaperDetail from './components/WallpaperDetail.vue'

const aggregations = ref(null)
const records = ref([])
const error = ref('')
const loading = ref(true)
const loadingMore = ref(false)
const loadedYears = new Set()
const filters = ref({ query: '', market: '', year: '', month: '', region: '', photographer: '', resolution: '' })
const selected = ref(null)
const aliasDict = ref(null) // 多语言地名词典（零结果建议 + 高亮桥接共用，懒加载）
const theme = ref('auto') // auto | light | dark
const index = computed(() => buildIndex(records.value))
const results = computed(() => searchRecords(index.value, records.value, filters.value.query, filters.value))
const suggestions = computed(() => {
  if (results.value.length || !filters.value.query || !aliasDict.value) return []
  return suggestFromDict(filters.value.query, aliasDict.value)
})

// spec §8 惰性加载：首屏只载最新年份分片，切到其他年份增量加载，「全部年份」才全量
async function ensureYear(year) {
  const key = String(year)
  if (!aggregations.value || !key || loadedYears.has(key)) return
  loadedYears.add(key) // 先标记进行中：await 间隙快速再切同年会绕过 has 检查导致双载
  loadingMore.value = true
  try {
    const shards = await loadYearShards(aggregations.value, year)
    records.value = records.value.concat(shards)
  } catch (e) {
    loadedYears.delete(key) // 失败解除标记，下年切换可重试
    throw e
  } finally {
    loadingMore.value = false
  }
}

async function ensureAllYears() {
  loadingMore.value = true
  try {
    records.value = await loadAllRecords(aggregations.value)
    for (const y of aggregations.value.years || []) loadedYears.add(String(y.name))
  } finally {
    loadingMore.value = false
  }
}

watch(
  () => filters.value.year,
  (y) => (y ? ensureYear(y) : ensureAllYears()),
)

// 筛选状态 ↔ URL：刷新还原、分享直达；replaceState 不产生历史记录
watch(
  filters,
  (f) => {
    history.replaceState(null, '', encodeFilters(f) || location.pathname)
  },
  { deep: true },
)

// 零结果采样（console 起步）：观察用户搜不到的词，作为词典扩充依据
watch(results, (r) => {
  if (!r.length && filters.value.query) console.info('[zero-hit]', filters.value.query)
})

async function ensureDict() {
  if (aliasDict.value) return
  try {
    aliasDict.value = await (await fetch('./data/geo_aliases.json')).json()
  } catch {
    /* 词典缺失时建议/桥接高亮静默降级 */
  }
}

watch(
  () => [filters.value.query, results.value.length],
  ([q, n]) => {
    if (q && !n) ensureDict()
  },
)

const THEME_LABEL = { auto: '主题 · 自动', light: '主题 · 浅色', dark: '主题 · 深色' }
function toggleTheme() {
  theme.value = theme.value === 'auto' ? 'light' : theme.value === 'light' ? 'dark' : 'auto'
}
watch(
  theme,
  (t) => {
    if (t === 'auto') delete document.documentElement.dataset.theme // 属性存在但为空会让 :not([data-theme]) 失效
    else document.documentElement.dataset.theme = t
    localStorage.setItem('theme', t)
  },
  { immediate: true },
)

function pickSuggestion(s) {
  filters.value = { ...filters.value, query: s }
}

function randomPick() {
  const pool = results.value.length ? results.value : records.value
  if (pool.length) selected.value = pool[Math.floor(Math.random() * pool.length)]
}

function searchTag(tag) {
  filters.value = { ...filters.value, query: tag }
  selected.value = null
  window.scrollTo({ top: 0 })
}

onMounted(async () => {
  const stored = localStorage.getItem('theme')
  if (stored) theme.value = stored
  Object.assign(filters.value, decodeFilters(location.search)) // 分享链接/刷新还原
  try {
    aggregations.value = await loadAggregations()
    if (!filters.value.year) {
      const latest = (aggregations.value.years || []).at(-1)?.name
      // 只改 filters.year，由上面的 watch 统一触发加载（避免显式调用导致同分片重复载入）
      filters.value.year = latest ? String(latest) : ''
    } else {
      // URL 带年份时 watch 触发过早（aggregations 未就绪被 ensureYear 放弃），这里补加载
      await ensureYear(filters.value.year)
    }
  } catch (e) {
    error.value = `数据加载失败：${e.message}`
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <header class="site-header">
    <h1>Bing 壁纸图集</h1>
    <span v-if="aggregations" class="total">{{ aggregations.total }} 张 · 更新至 {{ aggregations.latest_date }}</span>
    <button class="theme-toggle" @click="toggleTheme">{{ THEME_LABEL[theme] }}</button>
  </header>
  <FilterBar :aggregations="aggregations" v-model:filters="filters" @random="randomPick" />
  <p v-if="loading" class="status">加载中…</p>
  <p v-if="loadingMore" class="status">正在加载更多年份…</p>
  <p v-if="error" class="status error">{{ error }}</p>
  <p v-if="suggestions.length" class="hint">
    没找到「{{ filters.query }}」，试试它的其他写法：
    <button v-for="s in suggestions" :key="s" @click="pickSuggestion(s)">{{ s }}</button>
  </p>
  <WallpaperGrid :records="results" :query="filters.query" :alias-data="aliasDict" @select="selected = $event" />
  <WallpaperDetail
    v-if="selected"
    :record="selected"
    :records="records"
    @close="selected = null"
    @select-sibling="selected = $event"
    @search="searchTag"
  />
  <footer class="site-footer">
    图片版权归 Microsoft 及原作者/图库所有，本站仅做元数据索引与链接。
  </footer>
</template>
