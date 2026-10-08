<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { RES_SUFFIX, imageUrl } from '../api'

const props = defineProps({ record: Object, records: Array })
const emit = defineEmits(['close', 'select-sibling', 'search'])

// tags 混着拉丁/假名别名，只展示含汉字的（规范中文名与字形变体），点击即按该地点搜索
const cjkTags = (props.record.tags || []).filter((t) => /[一-鿿]/.test(t))

const picked = ref('')
// 只暴露用户可选档位（thumb 是列表缩略图专用，spec §6.4 禁止展示），并按 uhd>fhd>hd 排序
const available = computed(() => Object.keys(RES_SUFFIX).filter((k) => props.record.resolutions?.[k] === true))
const viewRes = computed(() => picked.value || available.value[0] || 'fhd')
const siblings = computed(() =>
  props.records.filter((r) => r.imageKey && r.imageKey === props.record.imageKey && r.id !== props.record.id),
)
const viewSrc = computed(() => imageUrl(props.record.urlbase, RES_SUFFIX[viewRes.value] || '_1920x1080.jpg'))
const RES_LABEL = { uhd: '4K UHD (3840×2160)', fhd: '1920×1080', hd: '1366×768' }

function onKey(e) {
  if (e.key === 'Escape') emit('close')
}
onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <div class="overlay" @click.self="emit('close')">
    <div class="modal">
      <button class="close" aria-label="关闭" @click="emit('close')">✕</button>
      <img class="hero" :src="viewSrc" :alt="record.title || record.desc" />
      <div class="res-switch" v-if="available.length">
        <button v-for="k in available" :key="k" :class="{ active: k === viewRes }" @click="picked = k">
          {{ RES_LABEL[k] || k }}
        </button>
      </div>
      <h2>{{ record.title || record.desc }}</h2>
      <div v-if="cjkTags.length" class="tag-row">
        <button v-for="t in cjkTags" :key="t" @click="emit('search', t)">{{ t }}</button>
      </div>
      <dl class="facts">
        <dt>日期</dt><dd>{{ record.date }}（{{ record.market }}）</dd>
        <dt v-if="record.location.length">地点</dt><dd v-if="record.location.length">{{ record.location.join(' · ') }}</dd>
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
        <h3>同图其他市场</h3>
        <button v-for="s in siblings" :key="s.id" @click="emit('select-sibling', s)">
          {{ s.market }} · {{ s.date }} · {{ s.title || s.desc }}
        </button>
      </div>
    </div>
  </div>
</template>
