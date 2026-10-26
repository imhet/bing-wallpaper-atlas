<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { MARKET_LABEL, RES_SUFFIX, imageUrl } from '../api'

// 沉浸观赏：纯黑底大图铺满居中，信息条与光标空闲后自动隐藏。
// 键盘 ←/→ 切换、Esc 退出（capture 阶段接管并 stopPropagation，弹层的 Esc 关闭收不到）。
const props = defineProps({ records: Array, index: Number })
const emit = defineEmits(['close', 'update:index'])

const cur = computed(() => props.records[props.index])
const countLabel = computed(() => `${props.index + 1} / ${props.records.length}`)
const atStart = computed(() => props.index <= 0)
const atEnd = computed(() => props.index >= props.records.length - 1)
// 观赏档位固定 1080p（镜像深史记录无多档变体，直链原图），与详情弹层默认一致不拉 4K
const srcOf = (r) =>
  r.urlbase.startsWith('https://') ? r.urlbase : imageUrl(r.urlbase, RES_SUFFIX.fhd)
const src = computed(() => srcOf(cur.value))

function go(d) {
  const i = props.index + d
  if (i >= 0 && i < props.records.length) emit('update:index', i)
}

// 键盘在 capture 阶段接管：Esc 阻断传播，详情弹层不会连带关闭
function onKey(e) {
  if (e.key === 'Escape') {
    e.stopPropagation()
    return emit('close')
  }
  if (e.key === 'ArrowRight') go(1)
  else if (e.key === 'ArrowLeft') go(-1)
}

// 全屏跟随沉浸（不支持/被拒时静默降级为页面内铺满）
onMounted(() => {
  window.addEventListener('keydown', onKey, true)
  document.documentElement.requestFullscreen?.().catch(() => {})
})
onUnmounted(() => {
  window.removeEventListener('keydown', onKey, true)
  if (document.fullscreenElement) document.exitFullscreen().catch(() => {})
  clearTimeout(idleTimer)
  window.removeEventListener('mousemove', poke)
  window.removeEventListener('pointerdown', poke)
})

// 信息条/光标空闲隐藏：鼠标移动或按下即浮现，3 秒无操作淡出（触屏轻点即 pointerdown）
const idle = ref(false)
let idleTimer
function poke() {
  idle.value = false
  clearTimeout(idleTimer)
  idleTimer = setTimeout(() => (idle.value = true), 3000)
}
onMounted(() => {
  window.addEventListener('mousemove', poke)
  window.addEventListener('pointerdown', poke)
  poke()
})

// 预加载下一张：切换不白屏
watch(
  () => props.index,
  (i) => {
    const next = props.records[i + 1]
    if (next) new Image().src = srcOf(next)
  },
  { immediate: true },
)

// 左右滑动切换（pointer 统一触屏与桌面拖拽），阈值 60px 防误触
let dragX = null
function onPointerDown(e) {
  dragX = e.clientX
}
function onPointerUp(e) {
  if (dragX == null) return
  const dx = e.clientX - dragX
  dragX = null
  if (dx < -60) go(1)
  else if (dx > 60) go(-1)
}
</script>

<template>
  <div
    class="viewer"
    :class="{ 'viewer-idle': idle }"
    @pointerdown="onPointerDown"
    @pointerup="onPointerUp"
  >
    <img class="viewer-img" :src="src" :alt="cur.title || cur.desc" draggable="false" />
    <button class="viewer-close" aria-label="退出沉浸模式" @click="emit('close')">✕</button>
    <span class="viewer-count">{{ countLabel }}</span>
    <button class="viewer-nav prev" :disabled="atStart" aria-label="上一张" @click="go(-1)">‹</button>
    <button class="viewer-nav next" :disabled="atEnd" aria-label="下一张" @click="go(1)">›</button>
    <div class="viewer-meta">
      <h2>{{ cur.title || cur.desc }}</h2>
      <p>
        {{ [cur.date, MARKET_LABEL[cur.market] || cur.market, ...(cur.location || []), cur.photographer].filter(Boolean).join(' · ') }}
      </p>
    </div>
  </div>
</template>
