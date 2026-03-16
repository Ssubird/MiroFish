<template>
  <section class="control-shell">
    <header class="control-header">
      <div>
        <p class="eyebrow">SIMULATOR</p>
        <h2>持续世界模拟器</h2>
      </div>
      <button type="button" class="run-btn" :disabled="!canAdvance" @click="$emit('advance')">
        {{ busy ? '运行中...' : '同步并推进' }}
      </button>
    </header>

    <p v-if="runMessage" class="run-message">{{ runMessage }}</p>

    <div class="summary-grid">
      <article class="summary-card"><span>预算</span><strong>{{ budgetYuan }} 元</strong></article>
      <article class="summary-card"><span>并发</span><strong>x{{ llmParallelism }}</strong></article>
      <article class="summary-card"><span>讨论轮次</span><strong>{{ agentDialogueRounds }}</strong></article>
      <article class="summary-card"><span>已选 agent</span><strong>{{ selectedIds.length }}</strong></article>
    </div>

    <div class="field-grid">
      <label class="field">
        <span>购买预算</span>
        <input :value="budgetYuan" type="number" min="2" max="500" step="2" @input="$emit('update:budgetYuan', Number($event.target.value || 0))" />
      </label>
      <label class="field">
        <span>LLM 同阶段并发</span>
        <input :value="llmParallelism" type="number" min="1" max="32" @input="$emit('update:llmParallelism', Number($event.target.value || 1))" />
      </label>
      <label class="field">
        <span>讨论轮数</span>
        <input :value="agentDialogueRounds" type="number" min="0" max="3" @input="$emit('update:agentDialogueRounds', Number($event.target.value || 0))" />
      </label>
      <label class="toggle-field">
        <input :checked="liveInterviewEnabled" type="checkbox" @change="$emit('update:liveInterviewEnabled', $event.target.checked)" />
        <span>运行时启用人工互动记忆</span>
      </label>
    </div>

    <div class="field">
      <div class="field-head">
        <span>模型</span>
        <button type="button" class="ghost-btn" :disabled="llmModelLoading" @click="$emit('probe-model')">测试模型</button>
      </div>
      <select :value="selectedModelName" @change="$emit('update:selectedModelName', $event.target.value)">
        <option value="">使用默认模型</option>
        <option v-for="model in llmModels" :key="model.id || model.name" :value="model.id || model.name">
          {{ model.id || model.name }}
        </option>
      </select>
      <p v-if="modelProbeResult" class="muted">{{ modelProbeResult.message }}</p>
    </div>

    <div class="field">
      <div class="field-head">
        <span>生成型 agent</span>
        <button type="button" class="ghost-btn" @click="$emit('select-all')">全选</button>
      </div>
      <div class="strategy-grid">
        <label v-for="strategy in strategies" :key="strategy.strategy_id" class="strategy-card">
          <input
            :checked="selectedIds.includes(strategy.strategy_id)"
            type="checkbox"
            @change="$emit('toggle-strategy', strategy.strategy_id)"
          />
          <div>
            <strong>{{ strategy.display_name }}</strong>
            <p>{{ groupLabel(strategy.group) }} / {{ kindLabel(strategy.kind) }}</p>
          </div>
        </label>
      </div>
    </div>
  </section>
</template>

<script setup>
import { groupLabel, kindLabel } from '../utils/lotteryDisplay'

defineProps({
  strategies: { type: Array, default: () => [] },
  selectedIds: { type: Array, default: () => [] },
  budgetYuan: { type: Number, default: 50 },
  llmParallelism: { type: Number, default: 8 },
  agentDialogueRounds: { type: Number, default: 1 },
  liveInterviewEnabled: { type: Boolean, default: true },
  llmModels: { type: Array, default: () => [] },
  selectedModelName: { type: String, default: '' },
  modelProbeResult: { type: Object, default: null },
  llmModelLoading: { type: Boolean, default: false },
  runMessage: { type: String, default: '' },
  busy: { type: Boolean, default: false },
  canAdvance: { type: Boolean, default: false }
})

defineEmits([
  'advance',
  'probe-model',
  'select-all',
  'toggle-strategy',
  'update:budgetYuan',
  'update:llmParallelism',
  'update:agentDialogueRounds',
  'update:liveInterviewEnabled',
  'update:selectedModelName'
])
</script>

<style scoped>
.control-shell,
.summary-grid,
.field-grid,
.strategy-grid {
  display: grid;
  gap: 1rem;
}

.control-shell {
  padding: 1.25rem;
  border-radius: 1.5rem;
  border: 1px solid rgba(0, 240, 255, 0.15);
  background: rgba(11, 12, 16, 0.6);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  box-shadow: 0 20px 48px rgba(0, 0, 0, 0.5), inset 0 0 20px rgba(0, 240, 255, 0.05);
  color: #e0e6ed;
}

.control-header,
.field-head {
  display: flex;
  gap: 0.75rem;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
}

.summary-grid,
.field-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.summary-card,
.strategy-card {
  padding: 1rem;
  border-radius: 1rem;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.03);
  transition: all 0.3s ease;
}

.summary-card:hover,
.strategy-card:hover {
  background: rgba(255, 255, 255, 0.06);
  border-color: rgba(0, 240, 255, 0.2);
  box-shadow: 0 0 15px rgba(0, 240, 255, 0.1);
}

.field,
.toggle-field {
  display: grid;
  gap: 0.5rem;
}

.toggle-field {
  align-content: end;
}

.run-btn,
.ghost-btn,
input,
select {
  font: inherit;
}

.run-btn,
.ghost-btn {
  border-radius: 999px;
  padding: 0.6rem 1.2rem;
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
  font-weight: 600;
}

.ghost-btn {
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(255, 255, 255, 0.05);
  color: #a0b2c6;
}

.ghost-btn:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.1);
  color: #fff;
}

.ghost-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.run-btn {
  border: 1px solid rgba(0, 240, 255, 0.4);
  background: rgba(0, 240, 255, 0.1);
  color: #00f0ff;
  box-shadow: 0 0 15px rgba(0, 240, 255, 0.2), inset 0 0 10px rgba(0, 240, 255, 0.1);
}

.run-btn:hover:not(:disabled) {
  background: rgba(0, 240, 255, 0.2);
  box-shadow: 0 0 25px rgba(0, 240, 255, 0.4), inset 0 0 20px rgba(0, 240, 255, 0.2);
  transform: translateY(-2px);
  color: #fff;
}

.run-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  border-color: rgba(255, 255, 255, 0.1);
  background: rgba(255, 255, 255, 0.05);
  color: #8b9bb4;
  box-shadow: none;
}

.field input,
.field select {
  width: 100%;
  border-radius: 0.75rem;
  border: 1px solid rgba(255, 255, 255, 0.1);
  padding: 0.85rem 1rem;
  background: rgba(0, 0, 0, 0.3);
  color: #fff;
  transition: all 0.3s ease;
}

.field input:focus,
.field select:focus {
  outline: none;
  border-color: rgba(0, 240, 255, 0.5);
  box-shadow: 0 0 10px rgba(0, 240, 255, 0.2);
  background: rgba(0, 0, 0, 0.5);
}

.strategy-grid {
  grid-template-columns: 1fr;
  max-height: 36rem;
  overflow: auto;
  padding-right: 0.5rem;
}

/* Custom Scrollbar */
.strategy-grid::-webkit-scrollbar {
  width: 6px;
}
.strategy-grid::-webkit-scrollbar-track {
  background: rgba(255, 255, 255, 0.02);
  border-radius: 10px;
}
.strategy-grid::-webkit-scrollbar-thumb {
  background: rgba(0, 240, 255, 0.2);
  border-radius: 10px;
}
.strategy-grid::-webkit-scrollbar-thumb:hover {
  background: rgba(0, 240, 255, 0.4);
}

.strategy-card {
  display: flex;
  gap: 0.85rem;
  align-items: start;
  cursor: pointer;
}

.strategy-card input[type="checkbox"] {
  margin-top: 0.25rem;
  accent-color: #00f0ff;
  width: 1.1rem;
  height: 1.1rem;
}

.strategy-card input[type="checkbox"]:checked + div strong {
  color: #00f0ff;
  text-shadow: 0 0 8px rgba(0, 240, 255, 0.4);
}

.eyebrow,
.run-message,
.summary-card span,
.strategy-card p,
.muted {
  color: #8b9bb4;
  margin: 0;
}

.summary-card strong,
.strategy-card strong {
  display: block;
  margin-top: 0.25rem;
  font-size: 1.1rem;
  color: #fff;
}

.eyebrow,
.control-header h2 {
  margin: 0;
}

.control-header h2 {
  font-size: 1.5rem;
  font-weight: 700;
  color: #fff;
  letter-spacing: 0.02em;
}

@media (max-width: 960px) {
  .field-grid,
  .summary-grid {
    grid-template-columns: 1fr;
  }
}
</style>
