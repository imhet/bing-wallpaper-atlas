<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { RES_SUFFIX, imageUrl, mapsUrl, thumbUrl } from '../api'
import { favoriteKey } from '../favorites'
import { lang, marketLabel, regionLabel, t } from '../i18n'
import HeartIcon from './HeartIcon.vue'

const props = defineProps({ record: Object, records: Array, favKeys: Set, similarFor: Function })
const emit = defineEmits(['close', 'select-sibling', 'search', 'toggle-fav', 'immerse'])

const isFav = computed(() => props.favKeys.has(favoriteKey(props.record)))

// tags 混着拉丁/假名别名：中文界面只展示汉字写法（规范名与字形变体），英文界面展示拉丁写法
const placeTags = computed(() =>
  (props.record.tags || []).filter((tag) =>
    lang.value === 'en' ? /[a-z]/i.test(tag) : /[一-鿿]/.test(tag),
  ),
)
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
// 相似的图：图向量余弦近邻（App 传入 similarFor，索引未就绪/无向量时为空，区块整体隐藏）
const similarRecords = computed(() => (props.similarFor ? props.similarFor(props.record) : []))
const viewSrc = computed(() => imageUrl(props.record.urlbase, RES_SUFFIX[viewRes.value] || '_1920x1080.jpg'))
const RES_LABEL = computed(() => ({
  uhd: '4K UHD (3840×2160)',
  fhd: '1920×1080',
  hd: '1366×768',
  original: t('original'),
}))

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
      <div class="modal-top">
        <button
          class="fav-btn"
          :class="{ on: isFav }"
          :aria-label="isFav ? t('unfavorite') : t('favorite')"
          :title="isFav ? t('unfavorite') : t('favorite')"
          @click="emit('toggle-fav', record)"
        >
          <HeartIcon :class="{ on: isFav }" />
          {{ isFav ? t('faved') : t('favorite') }}
        </button>
        <button class="immerse-btn" @click="emit('immerse')">{{ t('immerse') }}</button>
        <button ref="closeBtn" class="close" :aria-label="t('close')" @click="emit('close')">✕</button>
      </div>
      <img class="hero" :src="viewSrc" :alt="record.title || record.desc" />
      <!-- 单档（镜像深史原图）也显示档位行，与新图格式一致 -->
      <div class="res-switch" v-if="available.length">
        <button v-for="k in available" :key="k" :class="{ active: k === viewRes }" @click="picked = k">
          {{ RES_LABEL[k] || k }}
        </button>
      </div>
      <h2 id="detail-title">{{ record.title || record.desc }}</h2>
      <div v-if="placeTags.length" class="tag-row">
        <button v-for="tag in placeTags" :key="tag" @click="emit('search', tag)">{{ tag }}</button>
      </div>
      <div v-if="contentTags.length" class="tag-row">
        <span class="content-label">{{ t('sceneLabel') }}</span>
        <button v-for="t in contentTags" :key="t" @click="emit('search', t)">{{ t }}</button>
      </div>
      <dl class="facts">
        <dt>{{ t('factDate') }}</dt><dd>{{ record.date }}（{{ marketLabel(record.market) }}）</dd>
        <dt v-if="record.location.length">{{ t('factLocation') }}</dt>
        <dd v-if="record.location.length"
          ><a class="loc-link" :href="mapsUrl(record.location)" target="_blank" rel="noopener"
            >{{ record.location.join(' · ') }} ↗</a
          ></dd
        >
        <dt v-if="record.region">{{ t('factRegion') }}</dt><dd v-if="record.region">{{ regionLabel(record.region) }}</dd>
        <dt v-if="record.photographer">{{ t('factPhotographer') }}</dt><dd v-if="record.photographer">{{ record.photographer }}</dd>
        <dt v-if="record.gallery">{{ t('factGallery') }}</dt><dd v-if="record.gallery">{{ record.gallery }}</dd>
      </dl>
      <div class="actions">
        <a v-for="k in available" :key="k" :href="imageUrl(record.urlbase, RES_SUFFIX[k] || `_${k}`)"
           target="_blank" rel="noopener">{{ t('download', { label: RES_LABEL[k] || k }) }}</a>
        <a v-if="record.copyrightlink" :href="record.copyrightlink" target="_blank" rel="noopener">{{ t('backstory') }}</a>
      </div>
      <div v-if="siblings.length" class="siblings">
        <h3>{{ t('siblings', { n: siblings.length }) }}</h3>
        <button v-for="s in siblings" :key="s.id" @click="emit('select-sibling', s)">
          {{ marketLabel(s.market) }} · {{ s.date }}
        </button>
      </div>
      <div v-if="similarRecords.length" class="siblings">
        <h3>{{ t('similar') }}</h3>
        <div class="similar-grid">
          <button
            v-for="s in similarRecords"
            :key="s.id"
            :title="s.title || s.desc"
            :aria-label="t('similarAria', { title: s.title || s.desc })"
            @click="emit('select-sibling', s)"
          >
            <img :src="thumbUrl(s)" :alt="s.title || s.desc" loading="lazy" decoding="async" />
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
