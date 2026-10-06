<script setup>
const props = defineProps({ aggregations: Object, filters: Object })
const emit = defineEmits(['update:filters'])

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
      @input="set('query', $event.target.value)"
    />
    <select :value="filters.market" @change="set('market', $event.target.value)">
      <option value="">全部市场</option>
      <option v-for="m in aggregations?.markets || []" :key="m" :value="m">{{ m }}</option>
    </select>
    <select :value="filters.year" @change="set('year', $event.target.value)">
      <option value="">全部年份</option>
      <option v-for="y in aggregations?.years || []" :key="y" :value="y">{{ y }}</option>
    </select>
    <select :value="filters.month" @change="set('month', $event.target.value)">
      <option value="">全部月份</option>
      <option v-for="m in 12" :key="m" :value="m">{{ m }} 月</option>
    </select>
    <select :value="filters.region" @change="set('region', $event.target.value)">
      <option value="">全部国家/地区</option>
      <option v-for="r in aggregations?.regions || []" :key="r.name" :value="r.name">
        {{ r.name }} ({{ r.count }})
      </option>
    </select>
    <select :value="filters.photographer" @change="set('photographer', $event.target.value)">
      <option value="">全部摄影师</option>
      <option v-for="p in aggregations?.photographers || []" :key="p.name" :value="p.name">
        {{ p.name }} ({{ p.count }})
      </option>
    </select>
    <select :value="filters.resolution" @change="set('resolution', $event.target.value)">
      <option value="">全部分辨率</option>
      <option value="uhd">4K UHD</option>
      <option value="fhd">1920×1080</option>
      <option value="hd">1366×768</option>
    </select>
  </div>
</template>
