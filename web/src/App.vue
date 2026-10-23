<script setup>
import { computed, onMounted, ref, shallowRef, watch } from 'vue'
import { dedupeByUrlbase, loadAggregations, loadAllRecords, loadYearShards } from './api'
import { applyFilters, buildIndex, parseDateQuery, searchRecords } from './search'
import { rrfFuse } from './semantic'
import { createSemanticEngine } from './semantic-engine'
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
const dataLoading = ref(false) // 全量分片后台补齐中：此窗口内搜索只覆盖部分数据，零结果不能报「没找到」
const filters = ref({ query: '', market: '', year: '', month: '', region: '', photographer: '', resolution: '' })
const selected = ref(null)
const aliasDict = ref(null) // 多语言地名词典（零结果建议 + 高亮桥接共用，懒加载）
const theme = ref('auto') // auto | light | dark
const index = computed(() => buildIndex(records.value))
const keywordResults = computed(() => searchRecords(index.value, records.value, filters.value.query, filters.value))
// 语义检索：模型与向量在空闲时后台加载，就绪后把关键词结果与语义结果做 RRF 融合；
// 未就绪/加载失败时 semanticScores 为空，结果就是纯关键词口径（渐进增强，不求人等）
const semanticEngine = shallowRef(null)
const semanticScores = shallowRef(null)
const semanticLoading = ref(false)
let semanticToken = 0
const results = computed(() => {
  if (!semanticScores.value?.size) return keywordResults.value
  return rrfFuse(
    applyFilters(records.value, filters.value),
    keywordResults.value.map((r) => r.id),
    semanticScores.value,
  )
})
// 渐进渲染：一次渲染几千张卡会让视口附近上百缩略图同时打 Bing CDN（HTTP/2 并发流被拒），
// 只渲染前 N 张，滚动到底自动追加；同图多市场版本先去重（代表 zh-cn 优先），免网格重复
const uniqueResults = computed(() => dedupeByUrlbase(results.value))
const VISIBLE_STEP = 120
// 一级首屏市场：中文用户主视角 + 深史最全的英文市场，gzip 后 ~90KB 慢链路 1~2 秒可出图
const FIRST_MARKETS = ['zh-cn', 'en-us']
const visibleCount = ref(VISIBLE_STEP)
const visibleResults = computed(() => uniqueResults.value.slice(0, visibleCount.value))
// 结果计数用去重后的图片数：与网格实际卡片口径一致（站头 total 是记录数）
const resultCount = computed(() => {
  const hasFilters = Object.values(filters.value).some(Boolean)
  const base = `${hasFilters ? '找到' : '共'} ${uniqueResults.value.length} 张`
  return dataLoading.value ? `${base}（数据加载中…）` : base
})
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
  // 全量补齐中零结果不代表搜不到，此时给「换个写法」建议会误导
  if (dataLoading.value || semanticLoading.value || results.value.length || !filters.value.query || !aliasDict.value) return []
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

// 语义引擎加载：全量数据补齐后空闲时启动，不跟首屏抢带宽
async function startSemantic() {
  if (semanticEngine.value || semanticLoading.value || !aggregations.value) return
  semanticLoading.value = true
  try {
    const years = [...new Set(Object.values(aggregations.value.years_by_market || {}).flat())]
    semanticEngine.value = await createSemanticEngine({ years })
  } catch (e) {
    console.warn('[semantic] 加载失败，退回关键词检索：', e)
  } finally {
    semanticLoading.value = false
  }
}
const whenIdle = (fn) => (window.requestIdleCallback ? requestIdleCallback(fn) : setTimeout(fn, 1500))

watch(
  [() => filters.value.query, semanticEngine],
  async ([q]) => {
    const engine = semanticEngine.value
    const token = ++semanticToken
    semanticScores.value = null
    // 日期查询是精确谓词，语义排序只会把无关图混进来
    if (!engine || !q.trim() || parseDateQuery(q)) return
    try {
      const scores = await engine.rank(q)
      if (token === semanticToken) semanticScores.value = scores
    } catch (e) {
      console.warn('[semantic] 查询编码失败，保留关键词结果：', e)
    }
  },
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
  const pool = uniqueResults.value.length ? uniqueResults.value : records.value
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
    // 分级加载三级：一级只等主视角市场（zh-cn/en-us）最新年分片先出图，二级补该年其余市场，
    // 三级后台全量——国内直连 github.io 吞吐只有几十 KB/s，六市场首屏批 3.3MB 会拖垮首屏。
    // 注意默认不把最新年写进 filters.year：搜索必须覆盖全历史（默认年份会把历史结果挡在墙外）
    const latest = Object.values(aggregations.value.years_by_market || {})
      .flat()
      .reduce((a, b) => Math.max(a, b), 0)
    const first = String(filters.value.year || latest || '')
    records.value = first ? await loadYearShards(aggregations.value, first, FIRST_MARKETS) : []
    let fullLoaded = false
    dataLoading.value = true
    if (first)
      loadYearShards(aggregations.value, first)
        .then((yearAll) => {
          if (!fullLoaded) records.value = yearAll // 全量先到则跳过（守卫：单年不得降级覆盖全量）
        })
        .catch(() => {})
    loadAllRecords(aggregations.value)
      .then((all) => {
        fullLoaded = true
        records.value = all
        dataLoading.value = false
        whenIdle(startSemantic)
      })
      .catch(() => {
        dataLoading.value = false
        console.warn('[backfill] 背景补齐失败，筛选计数暂为部分口径')
      })
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
  <p v-if="semanticLoading && filters.query && !results.length" class="hint">语义搜索准备中…</p>
  <p v-if="suggestions.length" class="hint">
    没找到「{{ filters.query }}」，试试它的其他写法：
    <button v-for="s in suggestions" :key="s" @click="pickSuggestion(s)">{{ s }}</button>
  </p>
  <p v-if="!loading && records.length" class="result-count">{{ resultCount }}</p>
  <WallpaperGrid
    :records="visibleResults"
    :query="filters.query"
    :alias-data="aliasDict"
    :data-loading="dataLoading"
    :loading="loading"
    @select="selected = $event"
  />
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
