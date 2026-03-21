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
      <div class="summary-block hot-label">
        <span>热号</span>
        <strong>{{ hotNumbers }}</strong>
      </div>
      <div class="summary-block cold-label">
        <span>冷号</span>
        <strong>{{ coldNumbers }}</strong>
      </div>
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
        <div class="number-top">
          <strong>{{ item.number }}</strong>
          <span class="count-badge">{{ item.count }}</span>
        </div>
        <div class="heat-track"><span :style="{ width: barWidth(item.count) }"></span></div>
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
const hotNumbers = computed(() => (props.stats?.hot_numbers || []).slice(0, 8).join(' / ') || '-')
const coldNumbers = computed(() => (props.stats?.cold_numbers || []).slice(0, 8).join(' / ') || '-')
const maxCount = computed(() => numbers.value.reduce((max, item) => Math.max(max, Number(item.count) || 0), 0))

function heatClass(count) {
  if (count >= 18) return 'hot'
  if (count >= 12) return 'warm'
  if (count <= 6) return 'cold'
  return 'normal'
}

function barWidth(count) {
  if (!maxCount.value) return '0%'
  const ratio = (Number(count) || 0) / maxCount.value
  return `${Math.max(20, Math.round(ratio * 100))}%`
}
</script>

<style scoped>
.board-shell {
  display: grid;
  gap: 1rem;
  padding: 1.15rem;
  border-radius: 1.5rem;
  border: 1px solid var(--lottery-line, rgba(88, 66, 39, 0.12));
  background: linear-gradient(180deg, rgba(255, 252, 247, 0.9), rgba(247, 240, 230, 0.92));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.48);
  color: var(--lottery-panel-ink, #2f251a);
}

.board-header,
.board-range {
  display: flex;
  gap: 0.75rem;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
}

.eyebrow {
  margin: 0;
  font-size: 0.76rem;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--lottery-accent-strong, #7e4b1d);
}

.board-header h3 {
  margin: 0;
  font-size: 1.3rem;
  font-weight: 700;
  color: var(--lottery-panel-ink, #2f251a);
}

.board-range {
  gap: 0.4rem;
  color: var(--lottery-muted, #6d5a48);
  font-size: 0.85rem;
}

.range-arrow { color: var(--lottery-accent, #a66a2c); }

.summary-row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.75rem;
  align-items: stretch;
}

.summary-block {
  display: grid;
  gap: 0.2rem;
  padding: 0.72rem 0.85rem;
  border-radius: 1rem;
  border: 1px solid transparent;
}

.summary-block span,
.summary-block strong {
  margin: 0;
  overflow-wrap: anywhere;
}

.summary-block span {
  font-size: 0.68rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  opacity: 0.82;
}

.summary-block strong {
  font-size: 0.84rem;
  line-height: 1.35;
}

.hot-label {
  background: linear-gradient(135deg, rgba(255, 241, 238, 0.98), rgba(255, 230, 225, 0.92));
  border-color: rgba(161, 63, 50, 0.18);
  color: var(--lottery-danger, #a13f32);
}

.cold-label {
  background: linear-gradient(135deg, rgba(236, 249, 246, 0.98), rgba(222, 244, 239, 0.92));
  border-color: rgba(47, 119, 107, 0.18);
  color: var(--lottery-teal, #2f776b);
}

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
  color: var(--lottery-teal, #2f776b);
  margin-bottom: 1rem;
  animation: subtleBreathe 3s ease-in-out infinite;
}

@keyframes subtleBreathe {
  0%, 100% { opacity: 0.5; transform: scale(1); }
  50% { opacity: 0.8; transform: scale(1.05); }
}

.empty-title {
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
  color: var(--lottery-panel-ink, #2f251a);
}

.empty-hint {
  margin: 0.3rem 0 0;
  color: var(--lottery-muted, #6d5a48);
  font-size: 0.82rem;
}

.number-grid {
  display: grid;
  grid-template-columns: repeat(10, minmax(0, 1fr));
  gap: 0.55rem;
}

.number-card {
  display: grid;
  gap: 0.34rem;
  padding: 0.56rem 0.46rem;
  border-radius: 0.9rem;
  border: 1px solid var(--lottery-line, rgba(88, 66, 39, 0.12));
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.82), rgba(249, 244, 236, 0.9));
  cursor: pointer;
  font: inherit;
  color: var(--lottery-muted, #6d5a48);
  transition: transform 0.22s ease, box-shadow 0.22s ease, border-color 0.22s ease;
  box-shadow: 0 6px 12px rgba(77, 57, 33, 0.04);
  text-align: left;
  animation: cardFadeIn 0.35s ease-out both;
}

.number-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.25rem;
}

.count-badge {
  flex-shrink: 0;
  min-width: 1.9rem;
  padding: 0.14rem 0.4rem;
  border-radius: 999px;
  background: rgba(33, 24, 15, 0.06);
  font-size: 0.64rem;
  font-weight: 700;
  text-align: center;
}

.heat-track {
  height: 0.28rem;
  border-radius: 999px;
  background: rgba(33, 24, 15, 0.08);
  overflow: hidden;
}

.heat-track span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: currentColor;
}

@keyframes cardFadeIn {
  from { opacity: 0; transform: translateY(4px); }
  to { opacity: 1; transform: translateY(0); }
}

.number-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 14px 24px rgba(77, 57, 33, 0.1);
  border-color: var(--lottery-line-strong, rgba(88, 66, 39, 0.2));
}

.number-card strong {
  font-size: 1.02rem;
  font-weight: 800;
  color: currentColor;
}

.number-card.hot {
  color: #8f2c22;
  background: linear-gradient(180deg, rgba(255, 241, 238, 0.96), rgba(255, 225, 219, 0.96));
  border-color: rgba(161, 63, 50, 0.24);
  box-shadow: 0 12px 22px rgba(161, 63, 50, 0.1);
}

.number-card.hot .count-badge { background: rgba(161, 63, 50, 0.14); }

.number-card.warm {
  color: #7e4b1d;
  background: linear-gradient(180deg, rgba(255, 247, 234, 0.96), rgba(247, 225, 187, 0.96));
  border-color: rgba(166, 106, 44, 0.24);
}

.number-card.warm .count-badge { background: rgba(166, 106, 44, 0.14); }

.number-card.normal {
  color: #6b5846;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.82), rgba(246, 239, 228, 0.92));
}

.number-card.cold {
  color: #1d6c60;
  background: linear-gradient(180deg, rgba(238, 249, 246, 0.96), rgba(219, 243, 238, 0.96));
  border-color: rgba(47, 119, 107, 0.24);
}

.number-card.cold .count-badge { background: rgba(47, 119, 107, 0.14); }

.number-card.selected {
  background: linear-gradient(135deg, #3b2a19, #7e4b1d);
  color: #fff;
  border-color: transparent;
  transform: translateY(-2px) scale(1.02);
  box-shadow: 0 16px 28px rgba(61, 42, 25, 0.24);
  z-index: 2;
}

.number-card.selected .count-badge {
  background: rgba(255, 255, 255, 0.16);
}

.number-card.selected .heat-track {
  background: rgba(255, 255, 255, 0.18);
}

.number-card.selected .heat-track span {
  background: #fff;
}

@media (max-width: 1080px) {
  .summary-row {
    grid-template-columns: 1fr;
  }
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
