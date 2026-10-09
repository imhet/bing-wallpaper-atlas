<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { loadAggregations, loadAllRecords, loadYearShards } from './api'
import { buildIndex, searchRecords } from './search'
import { computeFacets } from './facets'
import { encodeFilters, decodeFilters } from './urlState'
import { suggestFromDict } from './suggest'
import FilterBar from './components/FilterBar.vue'
import WallpaperGrid from './components/WallpaperGrid.vue'
import WallpaperDetail from './components/WallpaperDetail.vue'

const aggregations = ref(null)
const records = ref([])
const error = ref('')
const loading = ref(true)
const filters = ref({ query: '', market: '', year: '', month: '', region: '', photographer: '', resolution: '' })
const selected = ref(null)
const aliasDict = ref(null) // 多语言地名词典（零结果建议 + 高亮桥接共用，懒加载）
const theme = ref('auto') // auto | light | dark
const index = computed(() => buildIndex(records.value))
const results = computed(() => searchRecords(index.value, records.value, filters.value.query, filters.value))
// 渐进渲染：一次渲染几千张卡会让视口附近上百缩略图同时打 Bing CDN（HTTP/2 并发流被拒），
// 只渲染前 N 张，滚动到底自动追加
const VISIBLE_STEP = 120
const visibleCount = ref(VISIBLE_STEP)
const visibleResults = computed(() => results.value.slice(0, visibleCount.value))
watch(
  filters,
  () => {
    visibleCount.value = VISIBLE_STEP
  },
  { deep: true },
)
const sentinel = ref(null)
// 分面联动计数：每个下拉的计数 = 其他筛选 + 搜索词过滤后的分布（数据源为全量 records）
const facets = computed(() => computeFacets(index.value, records.value, filters.value.query, filters.value))
const suggestions = computed(() => {
  if (results.value.length || !filters.value.query || !aliasDict.value) return []
  return suggestFromDict(filters.value.query, aliasDict.value)
})

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
  // 滚动到底部附近就追加下一批卡片（rootMargin 提前预取，滚动无感）
  new IntersectionObserver(
    (entries) => {
      if (entries[0].isIntersecting && visibleCount.value < results.value.length)
        visibleCount.value += VISIBLE_STEP
    },
    { rootMargin: '800px' },
  ).observe(sentinel.value)
  try {
    aggregations.value = await loadAggregations()
    if (!filters.value.year) {
      const latest = Object.values(aggregations.value.years_by_market || {})
        .flat()
        .reduce((a, b) => Math.max(a, b), 0)
      if (latest) filters.value.year = String(latest) // 首屏默认展示最新年份
    }
    // 分级加载：首屏只等目标年份分片立刻渲染，其余分片后台补齐——
    // 全量 2.2MB 到齐才出图会拖垮慢网络首屏；补齐后分面计数自动修正为全量口径
    const first = String(filters.value.year || '')
    records.value = first ? await loadYearShards(aggregations.value, first) : []
    loadAllRecords(aggregations.value)
      .then((all) => {
        records.value = all
      })
      .catch(() => console.warn('[backfill] 背景补齐失败，筛选计数暂为部分口径'))
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
  <FilterBar :facets="facets" v-model:filters="filters" @random="randomPick" />
  <p v-if="loading" class="status">加载中…</p>
  <p v-if="error" class="status error">{{ error }}</p>
  <p v-if="suggestions.length" class="hint">
    没找到「{{ filters.query }}」，试试它的其他写法：
    <button v-for="s in suggestions" :key="s" @click="pickSuggestion(s)">{{ s }}</button>
  </p>
  <WallpaperGrid :records="visibleResults" :query="filters.query" :alias-data="aliasDict" @select="selected = $event" />
  <div ref="sentinel" aria-hidden="true"></div>
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
