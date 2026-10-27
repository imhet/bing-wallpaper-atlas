<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { MARKET_LABEL, thumbUrl } from '../api'
import { favoriteKey } from '../favorites'
import { groupByDate } from '../updates'
import HeartIcon from './HeartIcon.vue'

const props = defineProps({ records: Array, years: Array, loading: Boolean, favKeys: Set })
const emit = defineEmits(['select', 'toggle-fav'])

const year = ref(props.years[0] ? String(props.years[0]) : '')
// 一次渲染多天会让视口附近几十张缩略图同时打 Bing CDN，HTTP/2 并发流被拒 → 图片全空白
// （首页为此做渐进渲染，这里同理：先出 8 天 ≈ 40 张，滚动到底追加）
const STEP_DAYS = 8
const visibleDays = ref(STEP_DAYS)
const groups = computed(() =>
  groupByDate(year.value ? props.records.filter((r) => r.date.startsWith(year.value)) : props.records),
)
// 返回顶部：下滑超过一屏浮现，长列表翻几屏后一键回顶
const showTop = ref(false)
function backTop() {
  window.scrollTo({ top: 0, behavior: 'smooth' })
}
watch(year, () => {
  visibleDays.value = STEP_DAYS
})
const visibleGroups = computed(() => groups.value.slice(0, visibleDays.value))
// 骨架/淡入按记录 id 记（与 WallpaperGrid 同款，滚动追加不重复加载）
const loadedIds = ref(new Set())
const failedIds = ref(new Set())
const sentinel = ref(null)
// sentinel 在数据分支内（loading 时不渲染），IntersectionObserver 的挂载时机麻烦，
// scroll 监听 + 元素位置判断最直接；appending 防止惯性滚动期间连发事件一次性加完
let appending = false
async function onScroll() {
  showTop.value = window.scrollY > window.innerHeight
  if (appending) return
  const el = sentinel.value
  if (el && visibleDays.value < groups.value.length && el.getBoundingClientRect().top < window.innerHeight + 800) {
    appending = true
    visibleDays.value += STEP_DAYS
    await nextTick()
    appending = false
  }
}
onMounted(() => window.addEventListener('scroll', onScroll, { passive: true }))
onUnmounted(() => window.removeEventListener('scroll', onScroll))
</script>

<template>
  <div class="updates">
    <div class="updates-head">
      <select v-model="year" aria-label="选择年份">
        <option v-for="y in years" :key="y" :value="String(y)">{{ y }} 年</option>
      </select>
      <span class="updates-summary">{{ groups.length }} 天 · {{ groups.reduce((n, g) => n + g.items.length, 0) }} 张</span>
    </div>
    <p v-if="loading && !records.length" class="status">数据加载中…</p>
    <p v-else-if="!groups.length" class="empty">该年份暂无数据。</p>
    <template v-else>
      <section v-for="g in visibleGroups" :key="g.date" class="day-group">
        <h3>{{ g.date }} <span class="day-count">{{ g.items.length }} 张</span></h3>
        <div class="day-cards">
          <button v-for="r in g.items" :key="r.id" class="card" @click="emit('select', r)">
            <div class="thumb" :class="{ loaded: loadedIds.has(r.id), failed: failedIds.has(r.id) }">
              <span v-if="!loadedIds.has(r.id) && !failedIds.has(r.id)" class="skeleton" aria-hidden="true"></span>
              <img
                :src="thumbUrl(r)"
                :alt="r.title || r.desc"
                loading="lazy"
                decoding="async"
                @load="loadedIds.add(r.id)"
                @error="failedIds.add(r.id)"
              />
              <span v-if="failedIds.has(r.id)" class="thumb-fallback">{{ r.date }}</span>
              <span
                class="fav"
                :class="{ on: favKeys.has(favoriteKey(r)) }"
                role="button"
                :aria-label="favKeys.has(favoriteKey(r)) ? '取消收藏' : '收藏'"
                @click.stop="emit('toggle-fav', r)"
                ><HeartIcon /></span
              >
            </div>
            <div class="meta">
              <span class="market-badge" :data-market="r.market">{{ MARKET_LABEL[r.market] || r.market }}</span>
              <span class="title">{{ r.title || r.desc }}</span>
            </div>
          </button>
        </div>
      </section>
      <p v-if="visibleGroups.length < groups.length" class="hint">下滑加载更早的日期…</p>
      <div ref="sentinel" aria-hidden="true"></div>
    </template>
    <Transition name="fade">
      <button v-if="showTop" class="back-top" aria-label="返回顶部" @click="backTop">↑ 顶部</button>
    </Transition>
  </div>
</template>
