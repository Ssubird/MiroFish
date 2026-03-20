<template>
  <section class="workbench-shell">
    <header class="workbench-header">
      <div class="workbench-copy">
        <p class="eyebrow">WORLD WORKBENCH</p>
        <h2>执行工作台</h2>
        <p class="subtitle">控制参数、Agent 绑定和世界详情集中在同一个工作区里。</p>
      </div>

      <div class="workbench-actions">
        <div class="mode-switcher">
          <button
            v-for="mode in WORKBENCH_MODES"
            :key="mode.id"
            type="button"
            class="mode-btn"
            :class="{ active: workbenchMode === mode.id }"
            @click="$emit('update:workbenchMode', mode.id)"
          >
            {{ mode.label }}
          </button>
        </div>
        <button type="button" class="focus-btn" @click="$emit('toggle-maximize')">
          {{ expanded ? '还原双栏' : '放大工作台' }}
        </button>
      </div>
    </header>

    <div class="workbench-summary">
      <span>会话 {{ summary.sessionId || '-' }}</span>
      <span>阶段 {{ summary.phase || '-' }}</span>
      <span>已选 Agent {{ summary.selectedStrategies || 0 }}</span>
      <span>时间线 {{ summary.timelineCount || 0 }}</span>
      <span>模型 {{ summary.activeModel || '-' }}</span>
    </div>

    <div class="workbench-grid" :class="`mode-${workbenchMode}`">
      <div class="workbench-pane control-pane">
        <LotteryWorldControlPanel
          v-bind="controlProps"
          @advance="$emit('advance')"
          @sync-kuzu="$emit('sync-kuzu')"
          @load-models="$emit('load-models')"
          @probe-model="$emit('probe-model')"
          @select-all="$emit('select-all')"
          @toggle-strategy="$emit('toggle-strategy', $event)"
          @update:budgetYuan="$emit('update:budgetYuan', $event)"
          @update:llmParallelism="$emit('update:llmParallelism', $event)"
          @update:agentDialogueRounds="$emit('update:agentDialogueRounds', $event)"
          @update:visibleThroughPeriod="$emit('update:visibleThroughPeriod', $event)"
          @update:liveInterviewEnabled="$emit('update:liveInterviewEnabled', $event)"
          @update:selectedModelName="$emit('update:selectedModelName', $event)"
          @update:executionBinding="$emit('update:executionBinding', $event)"
          @reset:executionBindings="$emit('reset:executionBindings')"
        />
      </div>

      <div class="workbench-pane inspector-pane">
        <LotteryWorldInspector
          v-bind="inspectorProps"
          @refresh="$emit('refresh')"
          @reset="$emit('reset')"
          @interview="$emit('interview')"
          @update:agentId="$emit('update:agentId', $event)"
          @update:prompt="$emit('update:prompt', $event)"
          @view-details="$emit('view-details', $event)"
        />
      </div>
    </div>
  </section>
</template>

<script setup>
import LotteryWorldControlPanel from './LotteryWorldControlPanel.vue'
import LotteryWorldInspector from './LotteryWorldInspector.vue'

const WORKBENCH_MODES = [
  { id: 'split', label: '双栏' },
  { id: 'control', label: '控制' },
  { id: 'inspector', label: '详情' }
]

defineProps({
  workbenchMode: { type: String, default: 'split' },
  expanded: { type: Boolean, default: false },
  summary: { type: Object, default: () => ({}) },
  controlProps: { type: Object, default: () => ({}) },
  inspectorProps: { type: Object, default: () => ({}) }
})

defineEmits([
  'update:workbenchMode',
  'toggle-maximize',
  'advance',
  'sync-kuzu',
  'load-models',
  'probe-model',
  'select-all',
  'toggle-strategy',
  'update:budgetYuan',
  'update:llmParallelism',
  'update:agentDialogueRounds',
  'update:visibleThroughPeriod',
  'update:liveInterviewEnabled',
  'update:selectedModelName',
  'update:executionBinding',
  'reset:executionBindings',
  'refresh',
  'reset',
  'interview',
  'update:agentId',
  'update:prompt',
  'view-details'
])
</script>

<style scoped>
.workbench-shell {
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr);
  gap: 1rem;
  height: 100%;
  padding: 1.4rem;
  background: #f8f7f4;
}

.workbench-header,
.workbench-actions,
.workbench-summary {
  display: flex;
  gap: 0.75rem;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
}

.workbench-copy {
  display: grid;
  gap: 0.35rem;
  min-width: 0;
}

.eyebrow,
.subtitle,
.workbench-copy h2 {
  margin: 0;
}

.eyebrow,
.subtitle,
.workbench-summary {
  color: #666;
}

.workbench-copy h2 {
  font-size: 1.8rem;
  line-height: 1.05;
  color: #121212;
}

.subtitle {
  max-width: 40rem;
  line-height: 1.6;
}

.mode-switcher {
  display: flex;
  gap: 0.35rem;
  padding: 0.25rem;
  border-radius: 0.8rem;
  background: #efefef;
}

.mode-btn,
.focus-btn,
.workbench-summary span {
  border-radius: 999px;
  border: 1px solid #e3e3e3;
  background: #fff;
  padding: 0.45rem 0.8rem;
  font: inherit;
}

.mode-btn,
.focus-btn {
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.mode-btn.active {
  background: #121212;
  color: #fff;
  border-color: #121212;
}

.mode-btn:hover,
.focus-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 8px 18px rgba(18, 18, 18, 0.08);
}

.workbench-summary span {
  font-size: 0.82rem;
}

.workbench-grid {
  min-height: 0;
  display: grid;
  gap: 1rem;
}

.mode-split {
  grid-template-columns: minmax(22rem, 25rem) minmax(0, 1fr);
}

.mode-control {
  grid-template-columns: 1fr;
}

.mode-control .inspector-pane,
.mode-inspector .control-pane {
  display: none;
}

.mode-inspector {
  grid-template-columns: 1fr;
}

.workbench-pane {
  min-width: 0;
  min-height: 0;
  overflow: auto;
  padding-right: 0.35rem;
}

.workbench-pane::-webkit-scrollbar {
  width: 6px;
}

.workbench-pane::-webkit-scrollbar-thumb {
  border-radius: 999px;
  background: rgba(18, 18, 18, 0.14);
}

.workbench-pane :deep(.control-shell),
.workbench-pane :deep(.inspector-shell) {
  min-width: 0;
}

.workbench-pane :deep(.field-head),
.workbench-pane :deep(.inline-card),
.workbench-pane :deep(.section-head),
.workbench-pane :deep(.chip-row),
.workbench-pane :deep(.header-actions),
.workbench-pane :deep(.tab-bar) {
  flex-wrap: wrap;
}

.workbench-pane :deep(p),
.workbench-pane :deep(span),
.workbench-pane :deep(strong),
.workbench-pane :deep(small),
.workbench-pane :deep(button),
.workbench-pane :deep(.event-item),
.workbench-pane :deep(.log-item) {
  overflow-wrap: anywhere;
}

@media (max-width: 1240px) {
  .mode-split {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 960px) {
  .workbench-shell {
    padding: 1rem;
  }

  .workbench-copy h2 {
    font-size: 1.45rem;
  }
}
</style>
