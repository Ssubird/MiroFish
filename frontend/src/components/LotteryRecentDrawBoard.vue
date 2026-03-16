<template>
  <section class="board-shell">
    <header class="board-header">
      <div>
        <p class="eyebrow">RECENT 50</p>
        <h3>最近 50 期号码板</h3>
      </div>
      <div class="board-range">
        <span>{{ stats?.from_period || '-' }}</span>
        <span>→</span>
        <span>{{ stats?.to_period || '-' }}</span>
      </div>
    </header>

    <div class="summary-row">
      <span>热号：{{ (stats?.hot_numbers || []).slice(0, 8).join(' / ') || '-' }}</span>
      <span>冷号：{{ (stats?.cold_numbers || []).slice(0, 8).join(' / ') || '-' }}</span>
    </div>

    <div class="number-grid">
      <button
        v-for="item in numbers"
        :key="item.number"
        type="button"
        class="number-card"
        :class="[heatClass(item.count), { selected: item.number === selectedNumber }]"
        @click="$emit('select-number', item.number)"
      >
        <strong>{{ item.number }}</strong>
        <small>{{ item.count }} 次</small>
      </button>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  stats: { type: Object, default: () => ({ numbers: [] }) },
  selectedNumber: { type: Number, default: null }
})

defineEmits(['select-number'])

const numbers = computed(() => props.stats?.numbers || [])

function heatClass(count) {
  if (count >= 18) return 'hot'
  if (count >= 12) return 'warm'
  if (count <= 6) return 'cold'
  return 'normal'
}
</script>

<style scoped>
.board-shell {
  display: grid;
  gap: 1rem;
  padding: 1.15rem;
  border-radius: 1.4rem;
  border: 1px solid rgba(31, 28, 24, 0.1);
  background: rgba(255, 251, 244, 0.92);
  box-shadow: 0 18px 40px rgba(29, 27, 25, 0.08);
}

.board-header,
.summary-row,
.board-range {
  display: flex;
  gap: 0.8rem;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
}

.eyebrow,
.summary-row,
.board-range {
  color: #6e675f;
}

.eyebrow,
.board-header h3 {
  margin: 0;
}

.number-grid {
  display: grid;
  grid-template-columns: repeat(10, minmax(0, 1fr));
  gap: 0.65rem;
}

.number-card {
  display: grid;
  gap: 0.2rem;
  padding: 0.7rem 0.4rem;
  border-radius: 1rem;
  border: 1px solid rgba(31, 28, 24, 0.12);
  background: rgba(255, 255, 255, 0.92);
  cursor: pointer;
  font: inherit;
  color: #1d1b19;
}

.number-card strong {
  font-size: 1rem;
}

.number-card small {
  color: #6e675f;
}

.number-card.hot {
  background: rgba(205, 92, 66, 0.12);
}

.number-card.warm {
  background: rgba(210, 162, 55, 0.14);
}

.number-card.cold {
  background: rgba(71, 128, 191, 0.12);
}

.number-card.selected {
  border-color: rgba(24, 22, 19, 0.78);
  box-shadow: inset 0 0 0 1px rgba(24, 22, 19, 0.18);
}

@media (max-width: 980px) {
  .number-grid {
    grid-template-columns: repeat(8, minmax(0, 1fr));
  }
}

@media (max-width: 720px) {
  .number-grid {
    grid-template-columns: repeat(5, minmax(0, 1fr));
  }
}
</style>
