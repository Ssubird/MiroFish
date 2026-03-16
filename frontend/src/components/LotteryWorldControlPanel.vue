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
  gap: 0.95rem;
}

.control-shell {
  padding: 1.1rem;
  border-radius: 1.5rem;
  border: 1px solid rgba(31, 28, 24, 0.1);
  background: rgba(255, 251, 244, 0.92);
  box-shadow: 0 20px 48px rgba(29, 27, 25, 0.08);
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
  padding: 0.9rem;
  border-radius: 1rem;
  border: 1px solid rgba(31, 28, 24, 0.1);
  background: rgba(255, 255, 255, 0.92);
}

.field,
.toggle-field {
  display: grid;
  gap: 0.45rem;
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
  border: 1px solid rgba(31, 28, 24, 0.14);
  border-radius: 999px;
  padding: 0.6rem 1rem;
  background: rgba(255, 255, 255, 0.9);
  cursor: pointer;
}

.run-btn {
  background: #1d1b19;
  color: #fff;
}

.field input,
.field select {
  width: 100%;
  border-radius: 0.95rem;
  border: 1px solid rgba(31, 28, 24, 0.14);
  padding: 0.85rem 0.95rem;
  background: rgba(255, 255, 255, 0.94);
}

.strategy-grid {
  grid-template-columns: 1fr;
  max-height: 36rem;
  overflow: auto;
}

.strategy-card {
  display: flex;
  gap: 0.75rem;
  align-items: start;
}

.eyebrow,
.run-message,
.summary-card span,
.strategy-card p,
.muted {
  color: #6e675f;
  margin: 0;
}

.eyebrow,
.control-header h2 {
  margin: 0;
}

@media (max-width: 960px) {
  .field-grid,
  .summary-grid {
    grid-template-columns: 1fr;
  }
}
</style>
