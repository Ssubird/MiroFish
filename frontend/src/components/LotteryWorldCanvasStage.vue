<template>
  <section class="stage-shell">
    <header class="stage-header">
      <div class="stage-copy">
        <p class="eyebrow">WORLD GRAPH</p>
        <h2>图谱观察台</h2>
        <p class="subtitle">沿用原项目的图谱主位，下面直接挂最近 50 期号码板做联动观察。</p>
      </div>

      <div class="stage-actions">
        <span class="stage-pill">{{ sessionStatus || '未启动' }}</span>
        <button type="button" class="stage-btn" @click="$emit('toggle-maximize')">
          {{ expanded ? '还原双栏' : '放大图谱' }}
        </button>
      </div>
    </header>

    <div class="stage-metrics">
      <span>节点 {{ graph?.metrics?.node_count || 0 }}</span>
      <span>关系 {{ graph?.metrics?.edge_count || 0 }}</span>
      <span>预测 {{ predictedPeriod || '-' }}</span>
      <span>选中节点 {{ selectedNodeId || '-' }}</span>
    </div>

    <div class="stage-stack">
      <LotteryWorldGraph
        :graph="graph"
        :selected-node-id="selectedNodeId"
        @select-node="$emit('select-node', $event)"
      />
      <LotteryRecentDrawBoard
        :stats="recentDrawStats"
        :selected-number="selectedNumber"
        @select-number="$emit('select-number', $event)"
      />
    </div>
  </section>
</template>

<script setup>
import LotteryRecentDrawBoard from './LotteryRecentDrawBoard.vue'
import LotteryWorldGraph from './LotteryWorldGraph.vue'

defineProps({
  graph: { type: Object, default: () => ({ nodes: [], edges: [], metrics: {} }) },
  selectedNodeId: { type: String, default: '' },
  recentDrawStats: { type: Object, default: () => ({}) },
  selectedNumber: { type: Number, default: null },
  sessionStatus: { type: String, default: '' },
  predictedPeriod: { type: String, default: '' },
  expanded: { type: Boolean, default: false }
})

defineEmits(['select-node', 'select-number', 'toggle-maximize'])
</script>

<style scoped>
.stage-shell {
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr);
  gap: 1rem;
  height: 100%;
  padding: 1.4rem;
  background: #fff;
}

.stage-header,
.stage-actions,
.stage-metrics {
  display: flex;
  gap: 0.75rem;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
}

.stage-copy {
  display: grid;
  gap: 0.35rem;
  min-width: 0;
}

.eyebrow,
.subtitle,
.stage-copy h2 {
  margin: 0;
}

.eyebrow,
.subtitle,
.stage-metrics {
  color: #686868;
}

.stage-copy h2 {
  font-size: 1.8rem;
  line-height: 1.05;
  color: #121212;
}

.subtitle {
  max-width: 40rem;
  line-height: 1.6;
}

.stage-pill,
.stage-btn,
.stage-metrics span {
  border-radius: 999px;
  border: 1px solid #e6e6e6;
  background: #fafafa;
  padding: 0.45rem 0.85rem;
}

.stage-pill,
.stage-metrics span {
  font-size: 0.82rem;
}

.stage-btn {
  cursor: pointer;
  font: inherit;
  color: #121212;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.stage-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 8px 18px rgba(18, 18, 18, 0.08);
}

.stage-stack {
  min-height: 0;
  overflow: auto;
  display: grid;
  gap: 1rem;
  align-content: start;
  padding-right: 0.35rem;
}

.stage-stack::-webkit-scrollbar {
  width: 6px;
}

.stage-stack::-webkit-scrollbar-thumb {
  border-radius: 999px;
  background: rgba(18, 18, 18, 0.14);
}

@media (max-width: 960px) {
  .stage-shell {
    padding: 1rem;
  }

  .stage-copy h2 {
    font-size: 1.45rem;
  }
}
</style>
