<script setup>
import { ref } from 'vue'
import { thumbUrl } from '../api'
import { highlightParts } from '../search'

defineProps({ records: Array, query: String, aliasData: Object, dataLoading: Boolean, loading: Boolean })
const emit = defineEmits(['select'])

// 缩略图加载状态：骨架占位 → 淡入 / 失败兜底（按记录 id 记，滚动追加不重复加载）
const loadedIds = ref(new Set())
const failedIds = ref(new Set())
</script>

<template>
  <div class="grid">
    <button v-for="r in records" :key="r.id" class="card" @click="emit('select', r)">
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
      </div>
      <div class="meta">
        <span class="date">{{ r.date }}</span>
        <span class="title"
          ><template v-for="(p, i) in highlightParts(r.title || r.desc, query, aliasData)" :key="i"
            ><mark v-if="p.hit">{{ p.text }}</mark
            ><template v-else>{{ p.text }}</template></template
          ></span
        >
      </div>
    </button>
  </div>
  <!-- 首屏加载中由 App 的「加载中…」负责，不能同时说「没有匹配」 -->
  <p v-if="!records.length && !loading" class="empty">
    {{ dataLoading ? '数据仍在加载，请稍候…' : '没有匹配的壁纸，试试放宽筛选条件。' }}
  </p>
</template>
