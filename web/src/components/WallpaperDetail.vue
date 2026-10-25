<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { MARKET_LABEL, RES_SUFFIX, imageUrl, mapsUrl } from '../api'
import { favoriteKey } from '../favorites'
import HeartIcon from './HeartIcon.vue'

const props = defineProps({ record: Object, records: Array, favKeys: Set })
const emit = defineEmits(['close', 'select-sibling', 'search', 'toggle-fav'])

const isFav = computed(() => props.favKeys.has(favoriteKey(props.record)))

// tags 混着拉丁/假名别名，只展示含汉字的（规范中文名与字形变体），点击即按该地点搜索
const cjkTags = computed(() => (props.record.tags || []).filter((t) => /[一-鿿]/.test(t)))
// 内容标签（CLIP 打标）是词表中文概念词，全量展示
const contentTags = computed(() => props.record.content_tags || [])

const picked = ref('')
// 切换同图的其他市场版本后，原选中的档位可能不存在（镜像记录只有原图）
watch(
  () => props.record.id,
  () => {
    picked.value = ''
  },
)
// 只暴露用户可选档位（thumb 是列表缩略图专用，spec §6.4 禁止展示），并按 uhd>fhd>hd 排序；
// 镜像绝对 URL（npanuhin 深史）无多档变体，只有原图单档
const available = computed(() => {
  if (props.record.urlbase?.startsWith('https://'))
    return props.record.resolutions?.original ? ['original'] : []
  return Object.keys(RES_SUFFIX).filter((k) => props.record.resolutions?.[k] === true)
})
// 默认 1080p：uhd 一档动辄几 MB，移动端打开详情不应默认拉 4K
const viewRes = computed(() => {
  const avail = available.value
  return picked.value || (avail.includes('fhd') ? 'fhd' : avail[0] || 'fhd')
})
const siblings = computed(() =>
  props.records.filter((r) => r.imageKey && r.imageKey === props.record.imageKey && r.id !== props.record.id),
)
const viewSrc = computed(() => imageUrl(props.record.urlbase, RES_SUFFIX[viewRes.value] || '_1920x1080.jpg'))
const RES_LABEL = { uhd: '4K UHD (3840×2160)', fhd: '1920×1080', hd: '1366×768', original: '原图' }

const modalRef = ref(null)
const closeBtn = ref(null)
const lastFocus = ref(null)

function onKey(e) {
  if (e.key === 'Escape') return emit('close')
  if (e.key !== 'Tab' || !modalRef.value) return
  // 焦点陷阱：Tab 在弹层内循环，不逃到背后的卡片
  const items = [...modalRef.value.querySelectorAll('button, a[href], input')].filter((el) => !el.disabled)
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

onMounted(async () => {
  lastFocus.value = document.activeElement
  document.body.style.overflow = 'hidden'
  window.addEventListener('keydown', onKey)
  await nextTick()
  closeBtn.value?.focus()
})
onUnmounted(() => {
  window.removeEventListener('keydown', onKey)
  document.body.style.overflow = ''
  // 全量数据补齐会让去重代表切换，原卡片可能已被移出 DOM；此时把焦点还给网格里的任一张卡
  if (lastFocus.value?.isConnected) lastFocus.value.focus()
  else document.querySelector('.card')?.focus()
})
</script>

<template>
  <div class="overlay" @click.self="emit('close')">
    <div
      ref="modalRef"
      class="modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="detail-title"
    >
      <button ref="closeBtn" class="close" aria-label="关闭" @click="emit('close')">✕</button>
      <button
        class="fav-btn"
        :class="{ on: isFav }"
        :aria-label="isFav ? '取消收藏' : '收藏'"
        :title="isFav ? '取消收藏' : '收藏'"
        @click="emit('toggle-fav', record)"
      >
        <HeartIcon :class="{ on: isFav }" />
        {{ isFav ? '已收藏' : '收藏' }}
      </button>
      <img class="hero" :src="viewSrc" :alt="record.title || record.desc" />
      <!-- 单档（镜像深史原图）也显示档位行，与新图格式一致 -->
      <div class="res-switch" v-if="available.length">
        <button v-for="k in available" :key="k" :class="{ active: k === viewRes }" @click="picked = k">
          {{ RES_LABEL[k] || k }}
        </button>
      </div>
      <h2 id="detail-title">{{ record.title || record.desc }}</h2>
      <div v-if="cjkTags.length" class="tag-row">
        <button v-for="t in cjkTags" :key="t" @click="emit('search', t)">{{ t }}</button>
      </div>
      <div v-if="contentTags.length" class="tag-row">
        <span class="content-label">画面</span>
        <button v-for="t in contentTags" :key="t" @click="emit('search', t)">{{ t }}</button>
      </div>
      <dl class="facts">
        <dt>日期</dt><dd>{{ record.date }}（{{ record.market }}）</dd>
        <dt v-if="record.location.length">地点</dt>
        <dd v-if="record.location.length"
          ><a class="loc-link" :href="mapsUrl(record.location)" target="_blank" rel="noopener"
            >{{ record.location.join(' · ') }} ↗</a
          ></dd
        >
        <dt v-if="record.region">国家/地区</dt><dd v-if="record.region">{{ record.region }}</dd>
        <dt v-if="record.photographer">摄影师</dt><dd v-if="record.photographer">{{ record.photographer }}</dd>
        <dt v-if="record.gallery">图库</dt><dd v-if="record.gallery">{{ record.gallery }}</dd>
      </dl>
      <div class="actions">
        <a v-for="k in available" :key="k" :href="imageUrl(record.urlbase, RES_SUFFIX[k] || `_${k}`)"
           target="_blank" rel="noopener">下载 {{ RES_LABEL[k] || k }}</a>
        <a v-if="record.copyrightlink" :href="record.copyrightlink" target="_blank" rel="noopener">背后故事 ↗</a>
      </div>
      <div v-if="siblings.length" class="siblings">
        <h3>同图其他市场（{{ siblings.length }}）</h3>
        <button v-for="s in siblings" :key="s.id" @click="emit('select-sibling', s)">
          {{ MARKET_LABEL[s.market] || s.market }} · {{ s.date }}
        </button>
      </div>
    </div>
  </div>
</template>
