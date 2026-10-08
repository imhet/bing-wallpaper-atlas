<script setup>
const props = defineProps({ facets: Object, filters: Object })
const emit = defineEmits(['update:filters', 'random'])

// 分辨率档位 → 展示名（facet.name 是档位键）
const RES_LABEL = { uhd: '4K UHD', fhd: '1920×1080', hd: '1366×768' }

function set(key, value) {
  emit('update:filters', { ...props.filters, [key]: value })
}
</script>

<template>
  <div class="filter-bar">
    <input
      class="query"
      :value="filters.query"
      placeholder="搜索标题、地点、摄影师…（如：张家界 雪山）"
      aria-label="搜索"
      @input="set('query', $event.target.value)"
    />
    <select aria-label="市场" :value="filters.market" @change="set('market', $event.target.value)">
      <option value="">全部市场</option>
      <option v-for="m in facets?.market || []" :key="m.name" :value="m.name">
        {{ m.name }} ({{ m.count }})
      </option>
    </select>
    <select aria-label="年份" :value="filters.year" @change="set('year', $event.target.value)">
      <option value="">全部年份</option>
      <option v-for="y in facets?.year || []" :key="y.name" :value="y.name">
        {{ y.name }} ({{ y.count }})
      </option>
    </select>
    <select aria-label="月份" :value="filters.month" @change="set('month', $event.target.value)">
      <option value="">全部月份</option>
      <option v-for="m in facets?.month || []" :key="m.name" :value="m.name">
        {{ m.name }} 月 ({{ m.count }})
      </option>
    </select>
    <select aria-label="国家/地区" :value="filters.region" @change="set('region', $event.target.value)">
      <option value="">全部国家/地区</option>
      <option v-for="r in facets?.region || []" :key="r.name" :value="r.name">
        {{ r.name }} ({{ r.count }})
      </option>
    </select>
    <select aria-label="摄影师" :value="filters.photographer" @change="set('photographer', $event.target.value)">
      <option value="">全部摄影师</option>
      <option v-for="p in facets?.photographer || []" :key="p.name" :value="p.name">
        {{ p.name }} ({{ p.count }})
      </option>
    </select>
    <select aria-label="分辨率" :value="filters.resolution" @change="set('resolution', $event.target.value)">
      <option value="">全部分辨率</option>
      <option v-for="r in facets?.resolution || []" :key="r.name" :value="r.name">
        {{ RES_LABEL[r.name] || r.name }} ({{ r.count }})
      </option>
    </select>
    <button aria-label="随机看一张" @click="emit('random')">🎲 随机看看</button>
  </div>
</template>

<style scoped>
.filter-bar button { background: var(--panel); color: inherit; border: 1px solid var(--border); border-radius: 6px; padding: 8px 10px; font-size: 14px; cursor: pointer; }
</style>
