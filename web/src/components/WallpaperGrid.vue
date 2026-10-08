<script setup>
import { thumbUrl } from '../api'
import { highlightParts } from '../search'

defineProps({ records: Array, query: String, aliasData: Object })
const emit = defineEmits(['select'])
</script>

<template>
  <div class="grid">
    <button v-for="r in records" :key="r.id" class="card" @click="emit('select', r)">
      <img :src="thumbUrl(r)" :alt="r.title || r.desc" loading="lazy" />
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
  <p v-if="!records.length" class="empty">没有匹配的壁纸，试试放宽筛选条件。</p>
</template>
