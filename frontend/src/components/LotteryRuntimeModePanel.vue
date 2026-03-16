<template>
  <section class="panel">
    <div class="panel-header">
      <div>
        <p class="eyebrow">RUNTIME</p>
        <h3>运行模式</h3>
      </div>
      <span class="mode-pill">{{ modelValue }}</span>
    </div>

    <div class="mode-grid">
      <button
        v-for="item in runtimeModes"
        :key="item.value"
        type="button"
        class="mode-card"
        :class="{ active: modelValue === item.value }"
        @click="$emit('update:modelValue', item.value)"
      >
        <strong>{{ item.label }}</strong>
        <span>{{ item.note }}</span>
      </button>
    </div>

    <div class="stats-grid">
      <article class="stat-card">
        <span>固定预热</span>
        <strong>{{ warmupSize }}</strong>
        <small>仅持续世界保留，写入世界记忆。</small>
      </article>
      <article class="stat-card">
        <span>实时访谈</span>
        <strong>{{ liveInterviewEnabled ? '开启' : '关闭' }}</strong>
        <small>在 `await_result` 和 `failed` 状态下也可追问。</small>
      </article>
    </div>

    <label class="switch-row">
      <input
        :checked="liveInterviewEnabled"
        type="checkbox"
        @change="$emit('update:liveInterviewEnabled', $event.target.checked)"
      />
      <span>运行时启用真人追问</span>
    </label>

    <p class="helper">
      `world_v1` 是当前主流程：保留状态、按日推进、自动结算上一期并继续讨论下一期。
      `legacy` 作为对照回测保留在高级路径里。
    </p>
  </section>
</template>

<script setup>
defineProps({
  modelValue: {
    type: String,
    default: 'world_v1'
  },
  warmupSize: {
    type: Number,
    default: 3
  },
  liveInterviewEnabled: {
    type: Boolean,
    default: true
  }
})

defineEmits(['update:modelValue', 'update:liveInterviewEnabled'])

const runtimeModes = [
  {
    value: 'world_v1',
    label: '持续世界',
    note: '持久状态、时间线、真人追问、购买委员会。'
  },
  {
    value: 'legacy',
    label: '经典回测',
    note: '保留原有滚动回测和图谱分支，供对照验证。'
  }
]
</script>

<style scoped>
.panel,
.stats-grid {
  display: grid;
  gap: 0.9rem;
}

.panel {
  padding: 1rem;
  border-radius: 1.25rem;
  border: 1px solid var(--lottery-line, rgba(31, 28, 24, 0.1));
  background: rgba(255, 255, 255, 0.72);
}

.panel-header,
.switch-row {
  display: flex;
  justify-content: space-between;
  gap: 0.8rem;
  align-items: center;
}

.eyebrow,
.helper,
.mode-card span,
.stat-card span,
.stat-card small {
  margin: 0;
  font-size: 0.8rem;
  line-height: 1.6;
  color: var(--lottery-muted, #6e675f);
}

.mode-pill,
.mode-card,
.stat-card {
  border-radius: 1rem;
  border: 1px solid var(--lottery-line-strong, rgba(31, 28, 24, 0.16));
}

.mode-pill {
  padding: 0.35rem 0.7rem;
  background: rgba(255, 255, 255, 0.85);
  font-size: 0.78rem;
}

.mode-grid,
.stats-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.mode-grid {
  display: grid;
  gap: 0.7rem;
}

.mode-card,
.stat-card {
  display: grid;
  gap: 0.35rem;
  padding: 0.95rem;
  background: rgba(255, 255, 255, 0.9);
}

.mode-card {
  text-align: left;
  cursor: pointer;
}

.mode-card.active {
  border-color: rgba(15, 118, 110, 0.38);
  background: linear-gradient(135deg, rgba(15, 118, 110, 0.12), rgba(255, 255, 255, 0.96));
}

.stat-card strong {
  font-size: 1.25rem;
}

.switch-row input {
  width: auto;
}

@media (max-width: 720px) {
  .mode-grid,
  .stats-grid {
    grid-template-columns: 1fr;
  }
}
</style>
