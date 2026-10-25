<script setup>
import { computed, onMounted, ref, shallowRef, watch } from 'vue'
import { dedupeByUrlbase, loadAggregations, loadAllRecords, loadYearShards } from './api'
import { applyFilters, buildIndex, extractGeoTerms, parseDateQuery, searchRecords } from './search'
import { geoFilterSemScores, rrfFuse } from './semantic'
import { createSemanticEngine } from './semantic-engine'
import { computeFacets } from './facets'
import { encodeFilters, decodeFilters } from './urlState'
import { suggestFromDict } from './suggest'
import { favoriteKey, loadFavorites, saveFavorites, toggleFavorite } from './favorites'
import HeartIcon from './components/HeartIcon.vue'
import FilterBar from './components/FilterBar.vue'
import WallpaperGrid from './components/WallpaperGrid.vue'
import WallpaperDetail from './components/WallpaperDetail.vue'
import UpdatesView from './components/UpdatesView.vue'

const aggregations = ref(null)
const records = ref([])
const error = ref('')
const loading = ref(true)
const dataLoading = ref(false) // 全量分片后台补齐中：此窗口内搜索只覆盖部分数据，零结果不能报「没找到」
const filters = ref({ query: '', market: '', year: '', month: '', region: '', photographer: '', resolution: '' })
const selected = ref(null)
const aliasDict = ref(null) // 多语言地名词典（零结果建议 + 高亮桥接共用，懒加载）
const theme = ref('auto') // auto | light | dark

// 本地收藏：key → 记录快照，localStorage 持久化。按图组归一键存，同图跨市场算同一张。
const favorites = ref(loadFavorites(localStorage))
watch(favorites, (f) => saveFavorites(localStorage, f))
const favKeys = computed(() => new Set(Object.keys(favorites.value)))
function toggleFav(record) {
  favorites.value = toggleFavorite(favorites.value, record)
}

// 视图切换：browse（搜索浏览）/ favorites（本地收藏）/ updates（更新日志）。
// favorites 是浏览器本地数据不入 URL；updates 入 URL 可分享直达
const view = ref('browse')
// 按收藏时间倒序——最后收藏的排最前（无 favAt 的旧数据沉底）
const favoriteRecords = computed(() => {
  const byKey = new Map(records.value.map((r) => [favoriteKey(r), r]))
  return Object.entries(favorites.value)
    .map(([key, snap]) => byKey.get(key) || snap)
    .sort((a, b) => (b.favAt || 0) - (a.favAt || 0))
})
const years = computed(() =>
  [...new Set(Object.values(aggregations.value?.years_by_market || {}).flat())].sort((a, b) => b - a),
)
// 站头口径与网格一致：去重后的图片数（记录数含跨市场重复，11236 vs 6762 两个数字打架让人困惑）
const totalImages = computed(() => dedupeByUrlbase(records.value).length)

const index = computed(() => buildIndex(records.value))
// 结果口径的唯一入口：关键词 + 语义融合（语义就绪时）。结果列表与分面计数都从这走，
// 保证「找到 N 张」和面板计数永远同源——搜「秋景」关键词层只命中 2 条、语义扩到 200 张，
// 计数若走纯关键词会全是 0/1，与列表完全脱节
function fusedResults(query, f) {
  const kw = searchRecords(index.value, records.value, query, f)
  if (!semanticScores.value?.size) return kw
  // 查询带地理限定词（如「中国的秋景」的「中国」）时约束语义候选：
  // CLIP 概念不懂国别，不过滤的话日本秋景会混进前排
  const semScores = geoFilterSemScores(semanticScores.value, records.value, extractGeoTerms(query, regionNames.value))
  return rrfFuse(
    applyFilters(records.value, f),
    kw.map((r) => r.id),
    semScores,
  )
}
// 语义检索：模型与向量在空闲时后台加载，就绪后把关键词结果与语义结果做 RRF 融合；
// 未就绪/加载失败时 semanticScores 为空，结果就是纯关键词口径（渐进增强，不求人等）
const semanticEngine = shallowRef(null)
const semanticScores = shallowRef(null)
const semanticLoading = ref(false)
let semanticToken = 0
const results = computed(() => fusedResults(filters.value.query, filters.value))
const regionNames = computed(() => [...new Set(records.value.map((r) => r.region).filter(Boolean))])
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
  if (view.value === 'favorites') return `共收藏 ${favoriteRecords.value.length} 张`
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
// 分面联动计数：与结果列表同口径（fusedResults），各维度轮流清空自身筛选重算分布
const facets = computed(() => computeFacets((f) => fusedResults(filters.value.query, f), filters.value))
const suggestions = computed(() => {
  // 全量补齐中零结果不代表搜不到，此时给「换个写法」建议会误导
  if (dataLoading.value || semanticLoading.value || results.value.length || !filters.value.query || !aliasDict.value) return []
  return suggestFromDict(filters.value.query, aliasDict.value)
})

// 筛选状态 ↔ URL：刷新还原、分享直达；replaceState 不产生历史记录。
// 只有 updates 入 URL（他人打开才有意义）；favorites 是本机数据，分享出去是空收藏只会困惑
watch(
  [filters, view],
  ([f, v]) => {
    const params = new URLSearchParams(encodeFilters(f).slice(1))
    if (v === 'updates') params.set('view', v)
    history.replaceState(null, '', params.toString() ? `?${params}` : location.pathname)
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
  const urlView = new URLSearchParams(location.search).get('view')
  if (urlView === 'updates') view.value = urlView
  // 滚动到底部附近就追加下一批卡片（rootMargin 提前预取，滚动无感）。
  // sentinel 只在浏览视图渲染（更新/收藏视图下为 null），用 watch 挂载
  const gridObserver = new IntersectionObserver(
    (entries) => {
      if (entries[0].isIntersecting && visibleCount.value < results.value.length)
        visibleCount.value += VISIBLE_STEP
    },
    { rootMargin: '800px' },
  )
  watch(sentinel, (el) => el && gridObserver.observe(el), { immediate: true })
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
    <h1><button class="home-link" title="回到浏览" @click="view = 'browse'">Bing 壁纸图集</button></h1>
    <button
      v-if="aggregations"
      class="theme-toggle total-link"
      :class="{ active: view === 'updates' }"
      @click="view = view === 'updates' ? 'browse' : 'updates'"
    >
      {{ view === 'updates' ? '← 返回浏览' : `${totalImages || aggregations.total} 张图 · 更新日志 →` }}
    </button>
    <button class="theme-toggle" :class="{ active: view === 'favorites' }" @click="view = view === 'favorites' ? 'browse' : 'favorites'">
      <HeartIcon :class="{ on: view === 'favorites' }" />
      {{ view === 'favorites' ? '返回浏览' : `收藏 ${favKeys.size}` }}
    </button>
    <button class="theme-toggle" @click="toggleTheme">{{ THEME_LABEL[theme] }}</button>
  </header>
  <UpdatesView
    v-if="view === 'updates'"
    :records="records"
    :years="years"
    :loading="loading || dataLoading"
    :fav-keys="favKeys"
    @select="selected = $event"
    @toggle-fav="toggleFav"
  />
  <template v-else>
    <FilterBar v-if="view === 'browse'" :facets="facets" v-model:filters="filters" @random="randomPick" />
    <p v-if="loading" class="status">加载中…</p>
    <p v-if="error" class="status error">{{ error }}</p>
    <p v-if="view === 'browse' && semanticLoading && filters.query && !results.length" class="hint">语义搜索准备中…</p>
    <p v-if="view === 'browse' && suggestions.length" class="hint">
      没找到「{{ filters.query }}」，试试它的其他写法：
      <button v-for="s in suggestions" :key="s" @click="pickSuggestion(s)">{{ s }}</button>
    </p>
    <p v-if="!loading && records.length" class="result-count">{{ resultCount }}</p>
    <p v-if="view === 'favorites' && !favoriteRecords.length" class="empty">
      还没有收藏。浏览时点卡片右上角的 ♥，喜欢的图就会留在这里（只存这台浏览器里）。
    </p>
    <WallpaperGrid
      :records="view === 'favorites' ? favoriteRecords : visibleResults"
      :query="view === 'favorites' ? '' : filters.query"
      :alias-data="aliasDict"
      :data-loading="dataLoading"
      :loading="loading"
      :fav-keys="favKeys"
      :hide-empty="view === 'favorites'"
      @select="selected = $event"
      @toggle-fav="toggleFav"
    />
    <div v-if="view === 'browse'" ref="sentinel" aria-hidden="true"></div>
  </template>
  <WallpaperDetail
    v-if="selected"
    :record="selected"
    :records="records"
    :fav-keys="favKeys"
    @close="selected = null"
    @select-sibling="selected = $event"
    @search="searchTag"
    @toggle-fav="toggleFav"
  />
  <footer class="site-footer">
    图片版权归 Microsoft 及原作者/图库所有，本站仅做元数据索引与链接。
  </footer>
</template>
