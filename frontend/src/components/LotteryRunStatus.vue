<template>
  <section v-if="status" class="panel" :class="status.state">
    <div class="panel-top">
      <div>
        <p class="eyebrow">RUN STATUS</p>
        <h2>{{ title }}</h2>
      </div>
      <span class="state-pill">{{ stateLabel }}</span>
    </div>

    <p class="message">{{ status.message }}</p>

    <div class="meta-grid">
      <article class="meta-card">
        <span>开始时间</span>
        <strong>{{ formatTime(status.startedAt) }}</strong>
      </article>
      <article class="meta-card">
        <span>结束时间</span>
        <strong>{{ status.finishedAt ? formatTime(status.finishedAt) : '进行中' }}</strong>
      </article>
      <article class="meta-card">
        <span>累计耗时</span>
        <strong>{{ liveDuration }}</strong>
      </article>
      <article class="meta-card">
        <span>结果摘要</span>
        <strong>{{ status.summary }}</strong>
      </article>
    </div>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { formatDurationLabel } from '../utils/lotteryDisplay'

const props = defineProps({
  status: {
    type: Object,
    default: null
  }
})

const now = ref(Date.now())
let timerId = null

const title = computed(() => {
  if (props.status?.state === 'running') return '任务正在执行'
  if (props.status?.state === 'success') return '任务已完成'
  if (props.status?.state === 'error') return '任务执行失败'
  return '任务状态'
})

const stateLabel = computed(() => {
  if (props.status?.state === 'running') return 'RUNNING'
  if (props.status?.state === 'success') return 'DONE'
  if (props.status?.state === 'error') return 'FAILED'
  return 'IDLE'
})

const liveDuration = computed(() => {
  if (!props.status) return '-'
  if (props.status.finishedAt) return formatDurationLabel(props.status.elapsedMs)
  return formatDurationLabel(now.value - props.status.startedAt)
})

const formatTime = (value) => (value ? new Date(value).toLocaleString() : '-')

const syncTimer = () => {
  if (timerId) {
    clearInterval(timerId)
    timerId = null
  }
  if (props.status?.state === 'running') {
    timerId = setInterval(() => {
      now.value = Date.now()
    }, 1000)
  }
}

watch(() => props.status?.state, syncTimer, { immediate: true })

onMounted(syncTimer)
onBeforeUnmount(() => {
  if (timerId) clearInterval(timerId)
})
</script>

<style scoped>
.panel {
  display: grid;
  gap: 1rem;
  padding: 1.35rem;
  border-radius: 1.5rem;
  border: 1px solid var(--lottery-line, rgba(31, 28, 24, 0.1));
  background: var(--lottery-panel, rgba(255, 251, 244, 0.92));
  box-shadow: var(--lottery-shadow, 0 18px 40px rgba(24, 22, 19, 0.08));
}

.panel.running {
  border-color: rgba(15, 118, 110, 0.24);
}

.panel.success {
  border-color: rgba(34, 94, 59, 0.24);
  background: linear-gradient(180deg, rgba(246, 255, 248, 0.98), rgba(255, 255, 255, 0.92));
}

.panel.error {
  border-color: rgba(180, 35, 24, 0.24);
  background: linear-gradient(180deg, rgba(255, 244, 241, 0.98), rgba(255, 255, 255, 0.92));
}

.panel-top {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: flex-start;
}

.eyebrow,
.message,
.meta-card span {
  margin: 0;
  font-size: 0.82rem;
  line-height: 1.6;
  color: var(--lottery-muted, #6e675f);
}

.message {
  max-width: 60rem;
}

.state-pill {
  display: inline-flex;
  align-items: center;
  padding: 0.45rem 0.8rem;
  border-radius: 999px;
  font-size: 0.78rem;
  letter-spacing: 0.08em;
  background: rgba(15, 118, 110, 0.08);
  border: 1px solid var(--lottery-line-strong, rgba(31, 28, 24, 0.16));
}

.meta-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0.85rem;
}

.meta-card {
  display: grid;
  gap: 0.35rem;
  padding: 1rem;
  border-radius: 1.1rem;
  border: 1px solid var(--lottery-line, rgba(31, 28, 24, 0.1));
  background: rgba(255, 255, 255, 0.72);
}

.meta-card strong {
  font-size: 1rem;
}

@media (max-width: 900px) {
  .meta-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .meta-grid {
    grid-template-columns: 1fr;
  }
}
</style>
