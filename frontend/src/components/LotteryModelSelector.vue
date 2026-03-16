<template>
  <section class="panel">
    <div class="panel-header">
      <div>
        <p class="eyebrow">MODEL HUB</p>
        <h2>模型选择</h2>
      </div>
      <div class="action-row">
        <button class="ghost-btn" :disabled="loading" @click="$emit('refresh')">
          {{ loading ? '读取中...' : '读取模型' }}
        </button>
        <button class="ghost-btn primary" :disabled="loading || !selectedModel" @click="$emit('probe')">
          测试当前模型
        </button>
      </div>
    </div>

    <label class="picker">
      <span>运行模型</span>
      <select :value="selectedModel" @change="updateModel">
        <option value="">使用 .env 默认模型</option>
        <option v-for="item in models" :key="item.id" :value="item.id">
          {{ item.id }}
        </option>
      </select>
    </label>

    <div class="meta-grid">
      <article class="meta-card">
        <span>默认模型</span>
        <strong>{{ defaultModel || '未设置' }}</strong>
      </article>
      <article class="meta-card">
        <span>可用模型数</span>
        <strong>{{ models.length }}</strong>
      </article>
      <article class="meta-card">
        <span>当前选择</span>
        <strong>{{ selectedModel || defaultModel || '未设置' }}</strong>
      </article>
    </div>

    <div v-if="probeResult" class="probe-card" :class="{ ok: probeResult.ok, fail: !probeResult.ok }">
      <strong>{{ probeResult.ok ? '模型探测通过' : '模型探测失败' }}</strong>
      <p>{{ probeResult.message }}</p>
    </div>
  </section>
</template>

<script setup>
defineProps({
  models: {
    type: Array,
    default: () => []
  },
  defaultModel: {
    type: String,
    default: ''
  },
  selectedModel: {
    type: String,
    default: ''
  },
  probeResult: {
    type: Object,
    default: null
  },
  loading: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:selectedModel', 'refresh', 'probe'])

const updateModel = (event) => {
  emit('update:selectedModel', event.target.value)
}
</script>

<style scoped>
.panel {
  display: grid;
  gap: 1rem;
  padding: 1.35rem;
  border-radius: 1.5rem;
  background: var(--lottery-panel, rgba(255, 251, 244, 0.92));
  border: 1px solid var(--lottery-line, rgba(31, 28, 24, 0.1));
  box-shadow: var(--lottery-shadow, 0 18px 40px rgba(24, 22, 19, 0.08));
}

.panel-header,
.action-row {
  display: flex;
  justify-content: space-between;
  gap: 0.8rem;
  align-items: center;
  flex-wrap: wrap;
}

.eyebrow,
.probe-card p,
.picker span,
.meta-card span {
  margin: 0;
  font-size: 0.82rem;
  line-height: 1.6;
  color: var(--lottery-muted, #6e675f);
}

.picker {
  display: grid;
  gap: 0.55rem;
}

.picker select {
  border-radius: 1rem;
  border: 1px solid var(--lottery-line-strong, rgba(31, 28, 24, 0.16));
  padding: 0.9rem 1rem;
  background: rgba(255, 255, 255, 0.9);
  font: inherit;
}

.meta-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.8rem;
}

.meta-card,
.probe-card {
  display: grid;
  gap: 0.35rem;
  padding: 1rem;
  border-radius: 1.1rem;
  border: 1px solid var(--lottery-line, rgba(31, 28, 24, 0.1));
  background: rgba(255, 255, 255, 0.72);
}

.probe-card.ok {
  border-color: rgba(34, 94, 59, 0.24);
  background: rgba(243, 255, 246, 0.92);
}

.probe-card.fail {
  border-color: rgba(180, 35, 24, 0.24);
  background: rgba(255, 245, 242, 0.92);
}

.ghost-btn {
  border: 1px solid var(--lottery-line-strong, rgba(31, 28, 24, 0.16));
  border-radius: 999px;
  padding: 0.65rem 0.95rem;
  background: rgba(255, 255, 255, 0.9);
  cursor: pointer;
  font: inherit;
}

.ghost-btn.primary {
  background: var(--lottery-ink, #1d1b19);
  color: #fff;
}

.ghost-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

@media (max-width: 720px) {
  .meta-grid {
    grid-template-columns: 1fr;
  }
}
</style>
