<template>
  <section class="preset-shell">
    <div class="preset-head">
      <div>
        <p class="eyebrow">QUICK START</p>
        <h3>一键预设</h3>
      </div>
      <span class="meta">{{ selectedCount }} / {{ totalCount }} agents</span>
    </div>

    <div class="preset-grid">
      <button
        v-for="item in presets"
        :key="item.id"
        type="button"
        class="preset-card"
        @click="$emit('applyPreset', item.id)"
      >
        <strong>{{ item.title }}</strong>
        <span>{{ item.note }}</span>
        <small>{{ item.stats }}</small>
      </button>
    </div>

    <div class="signal-row">
      <span>当前模式：{{ runtimeMode === 'world_v1' ? '持续世界' : '经典回测' }}</span>
      <span v-if="runtimeMode !== 'world_v1'">回测 {{ evaluationSize }} 期</span>
      <span>同阶段并发 x{{ llmParallelism }}</span>
      <span>预计请求 {{ estimatedCalls }}</span>
    </div>
  </section>
</template>

<script setup>
defineProps({
  runtimeMode: { type: String, default: 'world_v1' },
  evaluationSize: { type: Number, default: 3 },
  llmParallelism: { type: Number, default: 8 },
  estimatedCalls: { type: Number, default: 0 },
  selectedCount: { type: Number, default: 0 },
  totalCount: { type: Number, default: 0 }
})

defineEmits(['applyPreset'])

const presets = [
  {
    id: 'world-default',
    title: '标准推进',
    note: '持续世界默认配置，适合日常推进当前目标期。',
    stats: 'world_v1 / 对话 1 轮 / 并发 x8'
  },
  {
    id: 'deep-consensus',
    title: '深度讨论',
    note: '提高讨论强度和并发，适合正式推演。',
    stats: 'world_v1 / 对话 2 轮 / 并发 x10'
  },
  {
    id: 'fast-check',
    title: '经典回测',
    note: '保留 legacy 对照回测，入口收进次要位。',
    stats: 'legacy / 3 期 / 并发 x12'
  }
]
</script>

<style scoped>
.preset-shell,
.preset-grid {
  display: grid;
  gap: 0.9rem;
}

.preset-shell {
  padding: 1rem;
  border-radius: 1.35rem;
  border: 1px solid rgba(31, 28, 24, 0.08);
  background: linear-gradient(145deg, rgba(255, 255, 255, 0.82), rgba(244, 236, 222, 0.92));
}

.preset-head,
.signal-row {
  display: flex;
  justify-content: space-between;
  gap: 0.7rem;
  align-items: center;
  flex-wrap: wrap;
}

.eyebrow,
.preset-card span,
.preset-card small,
.signal-row span,
.meta {
  margin: 0;
  font-size: 0.8rem;
  line-height: 1.6;
  color: var(--lottery-muted, #6e675f);
}

.preset-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.preset-card {
  display: grid;
  gap: 0.45rem;
  padding: 1rem;
  text-align: left;
  border-radius: 1.15rem;
  border: 1px solid rgba(31, 28, 24, 0.1);
  background: rgba(255, 255, 255, 0.82);
  cursor: pointer;
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}

.preset-card:hover {
  transform: translateY(-2px);
  border-color: rgba(15, 118, 110, 0.28);
  box-shadow: 0 14px 28px rgba(15, 118, 110, 0.09);
}

.signal-row span,
.meta {
  padding: 0.35rem 0.72rem;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.76);
}

@media (max-width: 900px) {
  .preset-grid {
    grid-template-columns: 1fr;
  }
}
</style>
