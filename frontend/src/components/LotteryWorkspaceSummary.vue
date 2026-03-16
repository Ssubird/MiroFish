<template>
  <section class="panel">
    <div class="panel-header">
      <div>
        <p class="eyebrow">WORKSPACE</p>
        <h2>策略与图摘要</h2>
      </div>
      <span class="snapshot-id">{{ graph?.snapshot_id || 'graph-pending' }}</span>
    </div>

    <div class="top-grid">
      <article v-for="item in groupCards" :key="item.group" class="group-card">
        <span class="group-label">{{ item.label }}</span>
        <strong>{{ item.count }}</strong>
        <p>LLM {{ item.llmCount }} 个</p>
      </article>
    </div>

    <div class="meta-grid">
      <article class="meta-card"><span>本地快照节点</span><strong>{{ graph?.node_count ?? '-' }}</strong></article>
      <article class="meta-card"><span>本地快照关系</span><strong>{{ graph?.edge_count ?? '-' }}</strong></article>
      <article class="meta-card"><span>命盘文件</span><strong>{{ chartSummary?.total_charts ?? 0 }}</strong></article>
      <article class="meta-card"><span>有效命盘术语</span><strong>{{ chartSummary?.with_terms ?? 0 }}</strong></article>
    </div>

    <div class="meta-grid">
      <article class="meta-card"><span>Kuzu 图谱</span><strong>{{ kuzuStatus.available ? '已同步' : '未同步' }}</strong></article>
      <article class="meta-card"><span>Kuzu 节点 / 关系</span><strong>{{ `${kuzuStatus.node_count ?? 0} / ${kuzuStatus.edge_count ?? 0}` }}</strong></article>
      <article class="meta-card"><span>Zep 图谱</span><strong>{{ zepStatus.available ? '已同步' : '未同步' }}</strong></article>
      <article class="meta-card"><span>Zep 节点 / 关系</span><strong>{{ `${zepStatus.node_count ?? 0} / ${zepStatus.edge_count ?? 0}` }}</strong></article>
    </div>

    <div class="graph-card">
      <div class="section-head"><h3>高频图谱概念</h3><span>{{ graph?.highlights?.length || 0 }} 个词</span></div>
      <div class="chip-row">
        <span v-for="item in graph?.highlights || []" :key="item" class="chip">{{ item }}</span>
      </div>
      <div v-if="graph?.preview_relations?.length" class="relations-block">
        <div class="section-head"><h3>关系预览</h3><span>{{ graph.preview_relations.length }} 条</span></div>
        <ul><li v-for="item in graph.preview_relations" :key="item">{{ item }}</li></ul>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { groupLabel } from '../utils/lotteryDisplay'

const props = defineProps({ overview: { type: Object, default: null } })

const graph = computed(() => props.overview?.workspace_graph || null)
const chartSummary = computed(() => props.overview?.chart_summary || null)
const zepStatus = computed(() => props.overview?.zep_graph_status || {})
const kuzuStatus = computed(() => props.overview?.kuzu_graph_status || {})
const groupCards = computed(() => (
  Object.entries(props.overview?.strategy_group_summary || {}).map(([group, item]) => ({
    group,
    label: groupLabel(group),
    count: item.count,
    llmCount: item.llm_count
  }))
))
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
.section-head {
  display: flex;
  justify-content: space-between;
  gap: 0.8rem;
  align-items: center;
}

.eyebrow,
.snapshot-id,
.group-card p,
.meta-card span,
.section-head span,
.relations-block li {
  margin: 0;
  font-size: 0.82rem;
  line-height: 1.6;
  color: var(--lottery-muted, #6e675f);
}

.snapshot-id {
  padding: 0.45rem 0.8rem;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.72);
}

.top-grid,
.meta-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0.85rem;
}

.group-card,
.meta-card,
.graph-card {
  display: grid;
  gap: 0.35rem;
  padding: 1rem;
  border-radius: 1.15rem;
  border: 1px solid var(--lottery-line, rgba(31, 28, 24, 0.1));
  background: rgba(255, 255, 255, 0.72);
}

.group-card strong,
.meta-card strong {
  font-size: 1.4rem;
}

.group-label {
  color: var(--lottery-ink, #1d1b19);
  font-weight: 700;
}

.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.55rem;
}

.chip {
  display: inline-flex;
  align-items: center;
  padding: 0.36rem 0.75rem;
  border-radius: 999px;
  font-size: 0.8rem;
  color: var(--lottery-ink, #1d1b19);
  background: rgba(15, 118, 110, 0.08);
}

.relations-block ul {
  margin: 0;
  padding-left: 1rem;
  display: grid;
  gap: 0.55rem;
}

@media (max-width: 900px) {
  .top-grid,
  .meta-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .top-grid,
  .meta-grid {
    grid-template-columns: 1fr;
  }
}
</style>
