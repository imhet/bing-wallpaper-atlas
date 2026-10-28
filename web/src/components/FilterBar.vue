<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'

const props = defineProps({ facets: Object, filters: Object })
const emit = defineEmits(['update:filters', 'random'])

// 分辨率档位 → 展示名（facet.name 是档位键）
const RES_LABEL = { uhd: '4K UHD', fhd: '1920×1080', hd: '1366×768' }
const DIMS = [
  { key: 'market', label: '市场', all: '全部市场' },
  { key: 'year', label: '年份', all: '全部年份' },
  { key: 'month', label: '月份', all: '全部月份' },
  { key: 'region', label: '国家/地区', all: '全部国家/地区' },
  { key: 'photographer', label: '摄影师', all: '全部摄影师' },
  { key: 'resolution', label: '分辨率', all: '全部分辨率' },
]
// 摄影师有 4000+ 取值，面板默认只渲染前 100 项，靠关键字缩小范围
const LIMIT = 100

const open = ref('') // 当前展开面板的维度 key
const keyword = ref('')
const sheetRef = ref(null)
const lastTrigger = ref(null) // 关闭后把焦点还给触发的筛选按钮

// 面板打开时焦点移入（有关键字框则聚焦搜索框），并锁定背景滚动
watch(open, async (v) => {
  document.body.style.overflow = v ? 'hidden' : ''
  if (v) {
    await nextTick()
    sheetRef.value?.querySelector('.sheet-search, .option')?.focus()
  }
})
const current = computed(() => DIMS.find((d) => d.key === open.value))
const options = computed(() => props.facets?.[open.value] || [])
const matched = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return kw ? options.value.filter((o) => String(o.name).toLowerCase().includes(kw)) : options.value
})
const shown = computed(() => matched.value.slice(0, LIMIT))

function label(dim, value) {
  if (dim.key === 'resolution') return RES_LABEL[value] || value
  if (dim.key === 'month') return `${value} 月`
  return value
}
function btnText(dim) {
  return props.filters[dim.key] ? label(dim, String(props.filters[dim.key])) : dim.all
}
// 搜索防抖：逐键打字不触发全链路重算（fusedResults + 分面 6 维），停顿 200ms 才提交查询。
// 外部设置（点标签/建议词/URL 还原）绕过防抖立即生效
const rawQuery = ref(props.filters.query)
let debounceTimer = null
watch(
  () => props.filters.query,
  (v) => {
    clearTimeout(debounceTimer)
    rawQuery.value = v
  },
)
onUnmounted(() => clearTimeout(debounceTimer))
function set(key, value) {
  if (key !== 'query') return emit('update:filters', { ...props.filters, [key]: value })
  rawQuery.value = value
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => emit('update:filters', { ...props.filters, query: value }), 200)
}
function openSheet(key, e) {
  lastTrigger.value = e?.currentTarget || document.activeElement
  open.value = key
  keyword.value = ''
}
function closeSheet() {
  if (!open.value) return
  open.value = ''
  nextTick(() => lastTrigger.value?.focus())
}
function pick(value) {
  set(open.value, value)
  closeSheet()
}
function onKey(e) {
  if (!open.value) return
  if (e.key === 'Escape') return closeSheet()
  if (e.key !== 'Tab' || !sheetRef.value) return
  // 焦点陷阱：Tab 在面板内循环，不逃到背后的页面
  const items = [...sheetRef.value.querySelectorAll('button, input')].filter((el) => !el.disabled)
  if (!items.length) return
  const first = items[0]
  const last = items[items.length - 1]
  if (e.shiftKey && document.activeElement === first) {
    e.preventDefault()
    last.focus()
  } else if (!e.shiftKey && document.activeElement === last) {
    e.preventDefault()
    first.focus()
  }
}
onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => {
  window.removeEventListener('keydown', onKey)
  document.body.style.overflow = ''
})
</script>

<template>
  <div class="filter-bar">
    <input
      class="query"
      :value="rawQuery"
      placeholder="搜索标题、地点、画面内容…（如：中国 西藏 雪山；日期如 10-01）"
      aria-label="搜索"
      @input="set('query', $event.target.value)"
    />
    <button
      v-for="d in DIMS"
      :key="d.key"
      class="filter-btn"
      :class="{ active: filters[d.key] }"
      :aria-expanded="open === d.key"
      @click="openSheet(d.key, $event)"
    >
      <span class="filter-btn-text">{{ btnText(d) }}</span><span class="caret">▾</span>
    </button>
    <button aria-label="随机看一张" @click="emit('random')">🎲 随机看看</button>
  </div>
  <Teleport to="body">
    <div v-if="open" class="sheet-overlay" @click.self="closeSheet">
      <div ref="sheetRef" class="filter-sheet" role="dialog" :aria-label="current.label">
        <header class="sheet-head">
          <h3>{{ current.label }}</h3>
          <button class="sheet-close" aria-label="关闭" @click="closeSheet">✕</button>
        </header>
        <input
          v-if="options.length > 12"
          v-model="keyword"
          class="sheet-search"
          :placeholder="`搜索${current.label}…`"
        />
        <ul class="sheet-list">
          <li>
            <button class="option" :class="{ active: !filters[current.key] }" @click="pick('')">
              <span class="option-name">{{ current.all }}</span>
            </button>
          </li>
          <li v-for="o in shown" :key="o.name">
            <button
              class="option"
              :class="{ active: String(filters[current.key]) === String(o.name) }"
              @click="pick(String(o.name))"
            >
              <span class="option-name">{{ label(current, String(o.name)) }}</span>
              <span class="option-count">{{ o.count }}</span>
            </button>
          </li>
        </ul>
        <p v-if="!matched.length" class="sheet-empty">没有匹配的{{ current.label }}</p>
        <p v-else-if="matched.length > LIMIT" class="sheet-hint">仅显示前 {{ LIMIT }} 项，输入关键字可缩小范围</p>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.filter-bar button { background: var(--panel); color: inherit; border: 1px solid var(--border); border-radius: 6px; padding: 8px 10px; font-size: 14px; cursor: pointer; }
.filter-bar .filter-btn { display: inline-flex; align-items: center; gap: 6px; max-width: 220px; }
.filter-btn.active { border-color: var(--accent); color: var(--accent); }
.filter-btn-text { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.filter-btn .caret { color: var(--muted); font-size: 10px; flex: none; }

/* 面板从贴底改为屏幕中上（贴底是移动端 bottom-sheet 习惯，长列表下沿会被遮住）；
   超长内容靠 .sheet-list 的 overflow-y 滚动 */
.sheet-overlay { position: fixed; inset: 0; background: var(--overlay); z-index: 30; display: flex; align-items: flex-start; justify-content: center; padding-top: 12vh; }
.filter-sheet {
  background: var(--modal-bg); border: 1px solid var(--border); border-radius: 14px;
  width: min(100%, 560px); max-height: 70vh; display: flex; flex-direction: column; padding: 14px 16px 18px;
}
.sheet-head { display: flex; align-items: center; justify-content: space-between; }
.sheet-head h3 { margin: 0 0 10px; font-size: 16px; }
.sheet-close { background: var(--panel); color: inherit; border: 1px solid var(--border); border-radius: 6px; padding: 4px 10px; cursor: pointer; }
.sheet-search { background: var(--panel); color: inherit; border: 1px solid var(--border); border-radius: 6px; padding: 8px 10px; font-size: 14px; margin-bottom: 10px; }
.sheet-list { list-style: none; margin: 0; padding: 0; overflow-y: auto; flex: 1; }
.option {
  width: 100%; display: flex; gap: 10px; align-items: baseline; justify-content: space-between;
  text-align: left; background: none; color: inherit; border: 0; border-bottom: 1px solid var(--border);
  padding: 10px 4px; font-size: 14px; cursor: pointer;
}
.option.active { color: var(--accent); }
.option-name { overflow-wrap: anywhere; }
.option-count { color: var(--muted); font-size: 12px; flex: none; }
.sheet-empty, .sheet-hint { color: var(--muted); font-size: 12px; margin: 8px 0 0; }
@media (max-width: 620px) {
  .sheet-search { font-size: 16px; } /* 16px 防 iOS 聚焦自动放大 */
}
</style>
