<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { MARKET_LABEL, RES_SUFFIX, imageUrl } from '../api'
import { favoriteKey } from '../favorites'
import { fitScale } from '../fitScale'
import HeartIcon from './HeartIcon.vue'

// 沉浸观赏：纯黑底大图等比放大尽量铺满（fitScale：裁切超 20% 回退完整显示），
// 信息条与光标空闲后自动隐藏。
// 键盘 ←/→ 切换、↑ 收藏 ↓ 取消、Esc 退出（capture 阶段接管并 stopPropagation，弹层的 Esc 关闭收不到）。
// 切换必须等新图加载完成才替换显示：浏览器对改 src 的 img 会保留旧像素直到新图就绪，
// 直链切换会让画面滞留旧图（快连按看似「没动/翻到同一张」），慢网下尤其明显。
const props = defineProps({ records: Array, index: Number, favKeys: Set })
const emit = defineEmits(['close', 'update:index', 'toggle-fav'])

const cur = computed(() => props.records[props.index])
const countLabel = computed(() => `${props.index + 1} / ${props.records.length}`)
const atStart = computed(() => props.index <= 0)
const atEnd = computed(() => props.index >= props.records.length - 1)
const isFav = computed(() => props.favKeys.has(favoriteKey(cur.value)))
// 观赏档位固定 1080p（镜像深史记录无多档变体，直链原图），与详情弹层默认一致不拉 4K
const srcOf = (r) =>
  r.urlbase.startsWith('https://') ? r.urlbase : imageUrl(r.urlbase, RES_SUFFIX.fhd)

function go(d) {
  const i = props.index + d
  if (i >= 0 && i < props.records.length) emit('update:index', i)
}

// 收藏反馈：状态真正变化时从触发点（方向键则屏幕中央）飘出/收起一颗心
const bursts = ref([])
let burstId = 0
function favIf(state, pos) {
  if (props.favKeys.has(favoriteKey(cur.value)) === state) return
  const id = ++burstId
  bursts.value.push({ id, on: state, x: pos?.x ?? innerWidth / 2, y: pos?.y ?? innerHeight / 2 })
  setTimeout(() => (bursts.value = bursts.value.filter((b) => b.id !== id)), 900)
  emit('toggle-fav', cur.value)
}

// 键盘在 capture 阶段接管：Esc 阻断传播，详情弹层不会连带关闭
function onKey(e) {
  if (e.key === 'Escape') {
    e.stopPropagation()
    return emit('close')
  }
  if (e.key === 'ArrowRight') return go(1)
  if (e.key === 'ArrowLeft') return go(-1)
  if (e.key === 'ArrowUp') return favIf(true)
  if (e.key === 'ArrowDown') return favIf(false)
}

// 全屏跟随沉浸（不支持/被拒时静默降级为页面内铺满）
onMounted(() => {
  window.addEventListener('keydown', onKey, true)
  window.addEventListener('resize', resize)
  document.documentElement.requestFullscreen?.().catch(() => {})
})
onUnmounted(() => {
  window.removeEventListener('keydown', onKey, true)
  window.removeEventListener('resize', resize)
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

// 新图加载完成后才替换显示；未预加载的图等待期间显示 spinner（旧图保持原亮度，
// 不再压暗——预加载命中的瞬时切换被压暗就是「闪黑」的来源）。快连按只追最后一张（token 去抖）
const shownSrc = ref(props.records[props.index] ? srcOf(props.records[props.index]) : '')
const switching = ref(false)
let switchToken = 0
const preloaded = new Set()
watch(
  () => props.index,
  async (i) => {
    const target = props.records[i]
    if (!target) return
    const s = srcOf(target)
    const token = ++switchToken
    if (s === shownSrc.value) return
    if (!preloaded.has(s)) {
      switching.value = true
      try {
        await new Promise((ok, err) => {
          const im = new Image()
          im.onload = ok
          im.onerror = err
          im.src = s
        })
      } catch {
        /* 加载失败也切换：破图优于卡在旧图 */
      }
      if (token !== switchToken) return
    }
    shownSrc.value = s
    switching.value = false
  },
  { immediate: true },
)

// 预加载下一张：命中后切换零等待（也就没有 spinner/闪动）
watch(
  () => props.index,
  (i) => {
    const next = props.records[i + 1]
    if (!next) return
    const s = srcOf(next)
    const im = new Image()
    im.onload = () => preloaded.add(s)
    im.onerror = () => preloaded.add(s) // 失败也标记：重遇时直接切（反正是同一结果）
    im.src = s
  },
)

// 图片尺寸：fitScale 等比放大尽量铺满，按显示尺寸显式定位（object-fit 只能 contain/cover 二选一）
const imgEl = ref(null)
const imgStyle = ref({})
async function resize() {
  await nextTick()
  const im = imgEl.value
  if (!im?.naturalWidth) return
  const scale = fitScale(im.naturalWidth, im.naturalHeight, window.innerWidth, window.innerHeight)
  imgStyle.value = {
    width: `${Math.round(im.naturalWidth * scale)}px`,
    height: `${Math.round(im.naturalHeight * scale)}px`,
  }
}
watch(shownSrc, resize, { flush: 'post' })

// 进入时的操作提示：给新用户 2.5 秒看清按键，随后消失（不随 poke 重亮）
const hint = ref(true)
setTimeout(() => (hint.value = false), 2500)

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
    <img
      ref="imgEl"
      class="viewer-img"
      :style="imgStyle"
      :src="shownSrc"
      :alt="cur.title || cur.desc"
      draggable="false"
      @dblclick="favIf(!isFav, { x: $event.clientX, y: $event.clientY })"
    />
    <span
      v-for="b in bursts"
      :key="b.id"
      class="heart-burst"
      :class="{ on: b.on }"
      :style="{ left: `${b.x}px`, top: `${b.y}px` }"
      aria-hidden="true"
    >
      <HeartIcon class="burst-heart" :class="{ on: b.on }" />
    </span>
    <div v-if="switching" class="viewer-spinner" aria-hidden="true"></div>
    <div class="viewer-top">
      <button
        class="viewer-fav"
        :class="{ on: isFav }"
        :aria-label="isFav ? '取消收藏' : '收藏'"
        :title="isFav ? '取消收藏' : '收藏'"
        @click="favIf(!isFav)"
      >
        <HeartIcon :class="{ on: isFav }" />
        {{ isFav ? '已收藏' : '收藏' }}
      </button>
      <button class="viewer-close" aria-label="退出沉浸模式" @click="emit('close')">✕</button>
    </div>
    <span class="viewer-count">{{ countLabel }}</span>
    <button class="viewer-nav prev" :disabled="atStart" aria-label="上一张" @click="go(-1)">‹</button>
    <button class="viewer-nav next" :disabled="atEnd" aria-label="下一张" @click="go(1)">›</button>
    <div v-if="hint" class="viewer-hint">← → 切换 · 双击收藏 · ↑ 收藏 ↓ 取消 · Esc 退出</div>
    <div class="viewer-meta">
      <h2>{{ cur.title || cur.desc }}</h2>
      <p>
        {{ [cur.date, MARKET_LABEL[cur.market] || cur.market, ...(cur.location || []), cur.photographer].filter(Boolean).join(' · ') }}
      </p>
    </div>
  </div>
</template>
