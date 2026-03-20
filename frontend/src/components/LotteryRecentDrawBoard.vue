<template>
  <section class="board-shell">
    <header class="board-header">
      <div>
        <p class="eyebrow">RECENT 50</p>
        <h3>最近 50 期号码板</h3>
      </div>
      <div class="board-range">
        <span>{{ stats?.from_period || '-' }}</span>
        <span class="range-arrow">→</span>
        <span>{{ stats?.to_period || '-' }}</span>
      </div>
    </header>

    <div class="summary-row">
      <span class="hot-label">热号：{{ (stats?.hot_numbers || []).slice(0, 8).join(' / ') || '-' }}</span>
      <span class="cold-label">冷号：{{ (stats?.cold_numbers || []).slice(0, 8).join(' / ') || '-' }}</span>
    </div>

    <div v-if="!numbers.length" class="empty-state">
      <svg class="empty-icon" viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="8" y="8" width="20" height="20" rx="4" stroke="currentColor" stroke-width="1.5" opacity="0.2" />
        <rect x="36" y="8" width="20" height="20" rx="4" stroke="currentColor" stroke-width="1.5" opacity="0.15" />
        <rect x="8" y="36" width="20" height="20" rx="4" stroke="currentColor" stroke-width="1.5" opacity="0.15" />
        <rect x="36" y="36" width="20" height="20" rx="4" stroke="currentColor" stroke-width="1.5" opacity="0.1" />
        <text x="18" y="22" text-anchor="middle" fill="currentColor" font-size="10" opacity="0.25">8</text>
        <text x="46" y="22" text-anchor="middle" fill="currentColor" font-size="10" opacity="0.2">?</text>
      </svg>
      <p class="empty-title">号码数据待加载</p>
      <p class="empty-hint">推进模拟后，80 个号码的冷热分布将展示在此</p>
    </div>

    <div v-else class="number-grid">
      <button
        v-for="(item, index) in numbers"
        :key="item.number"
        type="button"
        class="number-card"
        :class="[heatClass(item.count), { selected: item.number === selectedNumber }]"
        :style="{ animationDelay: `${index * 8}ms` }"
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
  border-radius: 1.5rem;
  border: 1px solid rgba(0, 240, 255, 0.12);
  background: rgba(11, 12, 16, 0.65);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  box-shadow: 0 20px 48px rgba(0, 0, 0, 0.4), inset 0 0 16px rgba(0, 240, 255, 0.04);
  color: #e0e6ed;
}

.board-header,
.summary-row,
.board-range {
  display: flex;
  gap: 0.75rem;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
}

.eyebrow { margin: 0; color: #8b9bb4; }

.board-header h3 {
  margin: 0;
  font-size: 1.3rem;
  font-weight: 700;
  color: #fff;
}

.board-range {
  gap: 0.4rem;
  color: #6b7c8e;
  font-size: 0.85rem;
}

.range-arrow { color: #00f0ff; }

.summary-row {
  background: rgba(255, 255, 255, 0.025);
  padding: 0.6rem 0.85rem;
  border-radius: 0.75rem;
  border: 1px solid rgba(255, 255, 255, 0.05);
  font-size: 0.88rem;
  color: #8b9bb4;
}

.hot-label  { color: #ff6b6b; }
.cold-label { color: #00f0ff; }

/* ── Empty State ── */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 2.5rem 1rem;
  text-align: center;
}

.empty-icon {
  width: 4rem;
  height: 4rem;
  color: #5dd0ff;
  margin-bottom: 1rem;
  animation: subtleBreathe 3s ease-in-out infinite;
}

@keyframes subtleBreathe {
  0%, 100% { opacity: 0.5; transform: scale(1); }
  50%      { opacity: 0.8; transform: scale(1.05); }
}

.empty-title {
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
  color: #c8d6e5;
}

.empty-hint {
  margin: 0.3rem 0 0;
  color: #6b7c8e;
  font-size: 0.82rem;
}

/* ── Number Grid ── */
.number-grid {
  display: grid;
  grid-template-columns: repeat(10, minmax(0, 1fr));
  gap: 0.5rem;
}

.number-card {
  display: grid;
  gap: 0.15rem;
  padding: 0.55rem 0.25rem;
  border-radius: 0.6rem;
  border: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(0, 0, 0, 0.35);
  cursor: pointer;
  font: inherit;
  color: #e0e6ed;
  transition: all 0.25s cubic-bezier(0.175, 0.885, 0.32, 1.275);
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.15);
  text-align: center;
  animation: cardFadeIn 0.4s ease-out both;
}

@keyframes cardFadeIn {
  from { opacity: 0; transform: scale(0.9); }
  to   { opacity: 1; transform: scale(1); }
}

.number-card:hover {
  transform: translateY(-2px) scale(1.06);
  box-shadow: 0 6px 12px rgba(0, 0, 0, 0.25);
  border-color: rgba(255, 255, 255, 0.15);
}

.number-card strong {
  font-size: 1rem;
  font-weight: 700;
}

.number-card small {
  color: #6b7c8e;
  font-size: 0.68rem;
}

/* Heat classes */
.number-card.hot {
  background: rgba(255, 50, 50, 0.12);
  border-color: rgba(255, 50, 50, 0.3);
}
.number-card.hot:hover {
  box-shadow: 0 6px 16px rgba(255, 50, 50, 0.25);
  border-color: #ff3c3c;
}
.number-card.hot strong { color: #ff4444; text-shadow: 0 0 8px rgba(255, 50, 50, 0.4); }

.number-card.warm {
  background: rgba(255, 180, 0, 0.1);
  border-color: rgba(255, 180, 0, 0.3);
}
.number-card.warm:hover {
  box-shadow: 0 6px 16px rgba(255, 180, 0, 0.2);
}
.number-card.warm strong { color: #ffd700; text-shadow: 0 0 8px rgba(255, 180, 0, 0.4); }

.number-card.cold {
  background: rgba(0, 240, 255, 0.1);
  border-color: rgba(0, 240, 255, 0.25);
}
.number-card.cold:hover {
  box-shadow: 0 6px 16px rgba(0, 240, 255, 0.15);
}
.number-card.cold strong { color: #00f0ff; text-shadow: 0 0 8px rgba(0, 240, 255, 0.4); }

.number-card.selected {
  background: #fff;
  color: #000;
  border-color: #fff;
  transform: scale(1.1);
  box-shadow: 0 0 16px rgba(255, 255, 255, 0.5), inset 0 0 8px rgba(0, 0, 0, 0.15);
  z-index: 2;
}
.number-card.selected strong { text-shadow: none; color: #000; }
.number-card.selected small { color: #444; }

@media (max-width: 980px) {
  .number-grid { grid-template-columns: repeat(8, minmax(0, 1fr)); }
}

@media (max-width: 720px) {
  .number-grid { grid-template-columns: repeat(5, minmax(0, 1fr)); }
}
</style>
