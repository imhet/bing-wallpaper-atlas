<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { loadAggregations, loadAllRecords, loadYearShards } from './api'
import { buildIndex, searchRecords } from './search'
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
const index = computed(() => buildIndex(records.value))
const results = computed(() => searchRecords(index.value, records.value, filters.value.query, filters.value))

// spec §8 惰性加载：首屏只载最新年份分片，切到其他年份增量加载，「全部年份」才全量
async function ensureYear(year) {
  const key = String(year)
  if (!aggregations.value || !key || loadedYears.has(key)) return
  loadingMore.value = true
  try {
    const shards = await loadYearShards(aggregations.value, year)
    records.value = records.value.concat(shards)
    loadedYears.add(key)
  } finally {
    loadingMore.value = false
  }
}

async function ensureAllYears() {
  loadingMore.value = true
  try {
    records.value = await loadAllRecords(aggregations.value)
    for (const y of aggregations.value.years || []) loadedYears.add(String(y))
  } finally {
    loadingMore.value = false
  }
}

watch(
  () => filters.value.year,
  (y) => (y ? ensureYear(y) : ensureAllYears()),
)

onMounted(async () => {
  try {
    aggregations.value = await loadAggregations()
    const latest = (aggregations.value.years || []).at(-1)
    // 只改 filters.year，由上面的 watch 统一触发加载（避免显式调用导致同分片重复载入）
    filters.value.year = latest ? String(latest) : ''
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
    <span v-if="aggregations" class="total">{{ aggregations.total }} 张 · 每日自动更新</span>
  </header>
  <FilterBar :aggregations="aggregations" v-model:filters="filters" />
  <p v-if="loading" class="status">加载中…</p>
  <p v-if="loadingMore" class="status">正在加载更多年份…</p>
  <p v-if="error" class="status error">{{ error }}</p>
  <WallpaperGrid :records="results" @select="selected = $event" />
  <WallpaperDetail
    v-if="selected"
    :record="selected"
    :records="records"
    @close="selected = null"
    @select-sibling="selected = $event"
  />
  <footer class="site-footer">
    图片版权归 Microsoft 及原作者/图库所有，本站仅做元数据索引与链接。
  </footer>
</template>
