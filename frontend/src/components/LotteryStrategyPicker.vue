<template>
  <section class="panel">
    <div class="panel-header">
      <div>
        <p class="eyebrow">STRATEGIES</p>
        <h2>Agent 编排</h2>
      </div>
      <div class="meta-box">
        <strong>{{ selectedIds.length }}</strong>
        <span>/ {{ strategies.length }}</span>
      </div>
    </div>

    <div class="search-row">
      <input v-model.trim="query" type="search" placeholder="搜索 agent、描述或分组" />
      <button class="ghost-btn" type="button" @click="toggleFiltered">
        {{ allFilteredSelected ? '取消当前筛选' : '全选当前筛选' }}
      </button>
    </div>

    <div class="filter-block">
      <div class="filter-row">
        <button
          v-for="item in groupFilters"
          :key="item.value"
          type="button"
          class="filter-pill"
          :class="{ active: activeGroup === item.value }"
          @click="activeGroup = item.value"
        >
          {{ item.label }}
          <small>{{ item.count }}</small>
        </button>
      </div>
      <div class="filter-row">
        <button
          v-for="item in kindFilters"
          :key="item.value"
          type="button"
          class="filter-pill"
          :class="{ active: activeKind === item.value }"
          @click="activeKind = item.value"
        >
          {{ item.label }}
          <small>{{ item.count }}</small>
        </button>
      </div>
    </div>

    <div class="toolbar">
      <button class="ghost-btn" type="button" @click="toggleAll">
        {{ allSelected ? '清空全部' : '全选全部' }}
      </button>
      <span class="helper-text">
        当前筛选 {{ filteredStrategies.length }} 个，其中已选 {{ filteredSelectedCount }} 个。
      </span>
    </div>

    <div v-if="filteredStrategies.length" class="strategy-list">
      <label
        v-for="item in filteredStrategies"
        :key="item.strategy_id"
        class="strategy-card"
        :class="{ active: selectedIds.includes(item.strategy_id) }"
      >
        <input
          :checked="selectedIds.includes(item.strategy_id)"
          type="checkbox"
          @change="toggleOne(item.strategy_id)"
        />
        <div class="strategy-copy">
          <div class="strategy-top">
            <div>
              <strong>{{ item.display_name }}</strong>
              <p>{{ item.description }}</p>
            </div>
            <div class="tag-row">
              <span class="kind-tag" :class="item.kind">{{ kindLabel(item.kind) }}</span>
              <span class="group-tag">{{ groupLabel(item.group) }}</span>
            </div>
          </div>
          <div class="meta-row">
            <span>历史需求 {{ item.required_history }} 期</span>
            <span v-if="item.supports_dialogue">支持讨论</span>
            <span v-if="item.default_enabled">默认启用</span>
          </div>
        </div>
      </label>
    </div>

    <div v-else class="empty-state">
      当前筛选条件下没有可用策略。
    </div>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'

import { groupLabel, kindLabel } from '../utils/lotteryDisplay'

const props = defineProps({
  strategies: { type: Array, default: () => [] },
  selectedIds: { type: Array, default: () => [] }
})

const emit = defineEmits(['update:selectedIds'])

const query = ref('')
const activeGroup = ref('all')
const activeKind = ref('all')

const allSelected = computed(() => (
  props.strategies.length > 0
  && props.strategies.every((item) => props.selectedIds.includes(item.strategy_id))
))

const normalizedQuery = computed(() => query.value.trim().toLowerCase())

const filteredStrategies = computed(() => {
  return props.strategies.filter((item) => {
    if (activeGroup.value !== 'all' && item.group !== activeGroup.value) return false
    if (activeKind.value !== 'all' && item.kind !== activeKind.value) return false
    if (!normalizedQuery.value) return true
    const haystack = [item.display_name, item.description, item.group, item.kind].join(' ').toLowerCase()
    return haystack.includes(normalizedQuery.value)
  })
})

const filteredIds = computed(() => filteredStrategies.value.map((item) => item.strategy_id))

const filteredSelectedCount = computed(() => (
  filteredIds.value.filter((id) => props.selectedIds.includes(id)).length
))

const allFilteredSelected = computed(() => (
  filteredIds.value.length > 0 && filteredSelectedCount.value === filteredIds.value.length
))

const groupFilters = computed(() => {
  const counts = countBy(props.strategies, (item) => item.group)
  return [
    { value: 'all', label: '全部分组', count: props.strategies.length },
    ...counts.map((item) => ({ value: item.value, label: groupLabel(item.value), count: item.count }))
  ]
})

const kindFilters = computed(() => {
  const counts = countBy(props.strategies, (item) => item.kind)
  return [
    { value: 'all', label: '全部类型', count: props.strategies.length },
    ...counts.map((item) => ({ value: item.value, label: kindLabel(item.value), count: item.count }))
  ]
})

const toggleAll = () => {
  emit('update:selectedIds', allSelected.value ? [] : props.strategies.map((item) => item.strategy_id))
}

const toggleFiltered = () => {
  const next = new Set(props.selectedIds)
  if (allFilteredSelected.value) {
    filteredIds.value.forEach((id) => next.delete(id))
  } else {
    filteredIds.value.forEach((id) => next.add(id))
  }
  emit('update:selectedIds', [...next])
}

const toggleOne = (strategyId) => {
  const next = new Set(props.selectedIds)
  if (next.has(strategyId)) next.delete(strategyId)
  else next.add(strategyId)
  emit('update:selectedIds', [...next])
}

const countBy = (items, pick) => {
  const counts = new Map()
  items.forEach((item) => {
    const key = pick(item)
    counts.set(key, (counts.get(key) || 0) + 1)
  })
  return [...counts.entries()].map(([value, count]) => ({ value, count }))
}
</script>

<style scoped>
.panel,
.filter-block,
.filter-row,
.strategy-list {
  display: grid;
  gap: 0.9rem;
}

.panel {
  padding: 1.35rem;
  border-radius: 1.5rem;
  background: var(--lottery-panel, rgba(255, 251, 244, 0.92));
  border: 1px solid var(--lottery-line, rgba(31, 28, 24, 0.1));
  box-shadow: var(--lottery-shadow, 0 18px 40px rgba(24, 22, 19, 0.08));
}

.panel-header,
.toolbar,
.strategy-top,
.search-row {
  display: flex;
  justify-content: space-between;
  gap: 0.9rem;
  align-items: flex-start;
}

.search-row {
  align-items: center;
}

.search-row input {
  flex: 1;
  min-width: 0;
  padding: 0.86rem 1rem;
  border-radius: 1rem;
  border: 1px solid var(--lottery-line-strong, rgba(31, 28, 24, 0.16));
  background: rgba(255, 255, 255, 0.86);
  font: inherit;
}

.eyebrow,
.helper-text,
.meta-row,
.strategy-copy p,
.filter-pill small {
  margin: 0;
  font-size: 0.82rem;
  line-height: 1.6;
  color: var(--lottery-muted, #6e675f);
}

.meta-box {
  display: grid;
  place-items: center;
  min-width: 4.4rem;
  padding: 0.55rem 0.8rem;
  border-radius: 1rem;
  background: rgba(15, 118, 110, 0.09);
}

.ghost-btn,
.filter-pill {
  border: 1px solid var(--lottery-line-strong, rgba(31, 28, 24, 0.16));
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.84);
  cursor: pointer;
  font: inherit;
}

.ghost-btn {
  padding: 0.7rem 1rem;
}

.filter-row {
  grid-template-columns: repeat(auto-fit, minmax(7.5rem, max-content));
}

.filter-pill {
  display: inline-flex;
  gap: 0.4rem;
  align-items: center;
  justify-content: center;
  padding: 0.48rem 0.82rem;
}

.filter-pill.active {
  background: rgba(15, 118, 110, 0.1);
  border-color: rgba(15, 118, 110, 0.3);
}

.tag-row,
.meta-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.55rem;
}

.group-tag,
.kind-tag {
  display: inline-flex;
  align-items: center;
  padding: 0.28rem 0.7rem;
  border-radius: 999px;
  font-size: 0.76rem;
  border: 1px solid var(--lottery-line-strong, rgba(31, 28, 24, 0.16));
}

.group-tag {
  background: rgba(255, 255, 255, 0.72);
  color: var(--lottery-muted, #6e675f);
}

.kind-tag.llm {
  background: var(--lottery-ink, #1d1b19);
  color: #fff;
}

.kind-tag.rule {
  background: rgba(15, 118, 110, 0.1);
  color: var(--lottery-accent, #0f766e);
}

.strategy-list {
  max-height: 56rem;
  overflow: auto;
  padding-right: 0.2rem;
}

.strategy-card {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 0.85rem;
  padding: 1rem;
  border-radius: 1.2rem;
  border: 1px solid var(--lottery-line, rgba(31, 28, 24, 0.1));
  background: rgba(255, 255, 255, 0.72);
  cursor: pointer;
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}

.strategy-card:hover,
.strategy-card.active {
  transform: translateY(-1px);
  border-color: rgba(15, 118, 110, 0.35);
  box-shadow: 0 18px 30px rgba(15, 118, 110, 0.08);
}

.strategy-copy {
  display: grid;
  gap: 0.75rem;
}

.empty-state {
  padding: 1.15rem;
  border-radius: 1.1rem;
  border: 1px dashed var(--lottery-line-strong, rgba(31, 28, 24, 0.16));
  color: var(--lottery-muted, #6e675f);
}

@media (max-width: 900px) {
  .search-row,
  .toolbar,
  .strategy-top {
    flex-direction: column;
  }

  .strategy-list {
    max-height: none;
  }
}
</style>
