<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { MARKET_LABEL, thumbUrl } from '../api'
import { favoriteKey } from '../favorites'
import { groupByDate } from '../updates'

const props = defineProps({ records: Array, years: Array, loading: Boolean, favKeys: Set })
const emit = defineEmits(['select', 'toggle-fav'])

const year = ref(props.years[0] ? String(props.years[0]) : '')
// 一年的分组可能上百天 × 多市场，一次渲染会卡：先出 45 天，滚动到底追加
const visibleDays = ref(45)
const groups = computed(() =>
  groupByDate(year.value ? props.records.filter((r) => r.date.startsWith(year.value)) : props.records),
)
watch(year, () => {
  visibleDays.value = 45
})
const visibleGroups = computed(() => groups.value.slice(0, visibleDays.value))
const sentinel = ref(null)
// sentinel 在数据分支内（loading 时不渲染），IntersectionObserver 的挂载时机麻烦，
// scroll 监听 + 元素位置判断最直接；appending 防止惯性滚动期间连发事件一次性加完
let appending = false
async function onScroll() {
  if (appending) return
  const el = sentinel.value
  if (el && visibleDays.value < groups.value.length && el.getBoundingClientRect().top < window.innerHeight + 800) {
    appending = true
    visibleDays.value += 45
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
            <div class="thumb">
              <img :src="thumbUrl(r)" :alt="r.title || r.desc" loading="lazy" decoding="async" />
              <span
                class="fav"
                :class="{ on: favKeys.has(favoriteKey(r)) }"
                role="button"
                :aria-label="favKeys.has(favoriteKey(r)) ? '取消收藏' : '收藏'"
                @click.stop="emit('toggle-fav', r)"
                >♥</span
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
  </div>
</template>
