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
  gap: 1.25rem;
  padding: 1.25rem;
  border-radius: 1.5rem;
  border: 1px solid rgba(0, 240, 255, 0.15);
  background: rgba(11, 12, 16, 0.6);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  box-shadow: 0 20px 48px rgba(0, 0, 0, 0.5), inset 0 0 20px rgba(0, 240, 255, 0.05);
  color: #e0e6ed;
}

.board-header,
.summary-row,
.board-range {
  display: flex;
  gap: 1rem;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
}

.eyebrow,
.summary-row,
.board-range {
  color: #8b9bb4;
}

.eyebrow,
.board-header h3 {
  margin: 0;
}

.board-header h3 {
  font-size: 1.5rem;
  font-weight: 700;
  color: #fff;
  letter-spacing: 0.02em;
}

.board-range span:nth-child(2) {
  color: #00f0ff;
}

.summary-row {
  background: rgba(255, 255, 255, 0.03);
  padding: 0.75rem 1rem;
  border-radius: 1rem;
  border: 1px solid rgba(255, 255, 255, 0.05);
  font-size: 0.95rem;
}

.summary-row span:first-child {
  color: #ff6b6b;
}

.summary-row span:last-child {
  color: #00f0ff;
}

.number-grid {
  display: grid;
  grid-template-columns: repeat(10, minmax(0, 1fr));
  gap: 0.75rem;
}

.number-card {
  display: grid;
  gap: 0.25rem;
  padding: 0.75rem 0.4rem;
  border-radius: 0.75rem;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(0, 0, 0, 0.4);
  cursor: pointer;
  font: inherit;
  color: #e0e6ed;
  transition: all 0.25s cubic-bezier(0.175, 0.885, 0.32, 1.275);
  box-shadow: 0 4px 10px rgba(0, 0, 0, 0.2);
}

.number-card:hover {
  transform: translateY(-3px) scale(1.05);
  box-shadow: 0 8px 15px rgba(0, 0, 0, 0.3);
  border-color: rgba(255, 255, 255, 0.2);
}

.number-card strong {
  font-size: 1.15rem;
  font-weight: 700;
}

.number-card small {
  color: #8b9bb4;
  font-size: 0.75rem;
}

.number-card.hot {
  background: rgba(255, 60, 60, 0.15);
  border-color: rgba(255, 60, 60, 0.4);
  color: #ff8c8c;
}
.number-card.hot:hover {
  box-shadow: 0 8px 20px rgba(255, 60, 60, 0.3);
  border-color: #ff3c3c;
}
.number-card.hot strong { color: #ff3c3c; text-shadow: 0 0 10px rgba(255, 60, 60, 0.5); }

.number-card.warm {
  background: rgba(255, 180, 0, 0.15);
  border-color: rgba(255, 180, 0, 0.4);
  color: #ffd700;
}
.number-card.warm:hover {
  box-shadow: 0 8px 20px rgba(255, 180, 0, 0.2);
}
.number-card.warm strong { color: #ffd700; text-shadow: 0 0 10px rgba(255, 180, 0, 0.5); }

.number-card.cold {
  background: rgba(0, 240, 255, 0.15);
  border-color: rgba(0, 240, 255, 0.3);
  color: #80f8ff;
}
.number-card.cold:hover {
  box-shadow: 0 8px 20px rgba(0, 240, 255, 0.2);
}
.number-card.cold strong { color: #00f0ff; text-shadow: 0 0 10px rgba(0, 240, 255, 0.5); }

.number-card.selected {
  background: #fff;
  color: #000;
  border-color: #fff;
  transform: scale(1.1);
  box-shadow: 0 0 20px rgba(255, 255, 255, 0.6), inset 0 0 10px rgba(0, 0, 0, 0.2);
  z-index: 2;
}
.number-card.selected strong {
  text-shadow: none;
  color: #000;
}
.number-card.selected small {
  color: #444;
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
