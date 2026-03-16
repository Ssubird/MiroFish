<template>
  <section class="panel">
    <div class="panel-header">
      <div>
        <p class="eyebrow">PROCESS</p>
        <h2>工作区与运行轨迹</h2>
      </div>
      <span class="panel-meta">{{ documents.length }} 份文档 / {{ steps.length }} 个阶段</span>
    </div>

    <div class="summary-grid">
      <article class="summary-card">
        <span>已开奖</span>
        <strong>{{ overview?.completed_draws ?? '-' }}</strong>
      </article>
      <article class="summary-card">
        <span>待预测</span>
        <strong>{{ overview?.pending_draws ?? '-' }}</strong>
      </article>
      <article class="summary-card">
        <span>文档总数</span>
        <strong>{{ overview?.document_summary?.total_documents ?? '-' }}</strong>
      </article>
      <article class="summary-card">
        <span>当前目标期</span>
        <strong>{{ overview?.pending_target_draw?.period ?? '-' }}</strong>
      </article>
    </div>

    <div class="signal-row">
      <span v-if="llmStatus">LLM {{ llmStatus.configured ? '已配置' : '未配置' }} / {{ llmStatus.model || '未设置' }}</span>
      <span v-if="graphSummary">本地图谱 {{ graphSummary.snapshot_id }} / {{ graphSummary.node_count }} 节点</span>
      <span>命盘 {{ chartSummary?.total_charts ?? 0 }} 份</span>
      <span v-if="evaluation">模式 {{ runtimeLabel(evaluation.runtime_mode) }}</span>
      <span v-if="evaluation?.world_mode">世界 {{ evaluation.world_mode }}</span>
      <span v-if="evaluation">实时访谈 {{ evaluation.live_interview_enabled ? 'ON' : 'OFF' }}</span>
    </div>

    <div class="step-list">
      <article v-for="item in steps" :key="item.step || item.title" class="step-card">
        <div class="step-dot" :class="item.status"></div>
        <div class="step-body">
          <div class="step-head">
            <h3>{{ item.title }}</h3>
            <span>{{ item.status }}</span>
          </div>
          <p>{{ item.details }}</p>
          <div v-if="item.preview_periods?.length" class="chip-row">
            <span v-for="period in item.preview_periods" :key="period" class="chip solid">{{ period }}</span>
          </div>
          <div v-if="item.highlights?.length" class="chip-row">
            <span v-for="term in item.highlights" :key="term" class="chip">{{ term }}</span>
          </div>
          <p v-if="item.leader" class="leader-hint">当前领先 agent：{{ item.leader }}</p>
        </div>
      </article>
    </div>

    <div class="docs-card">
      <div class="docs-header">
        <h3>工作区文档</h3>
        <span v-if="loading">同步中...</span>
      </div>
      <div class="docs-list">
        <article v-for="doc in documents" :key="doc.path" class="doc-item">
          <div>
            <div class="doc-top">
              <strong>{{ doc.name }}</strong>
              <span class="doc-kind">{{ doc.kind }}</span>
            </div>
            <p>{{ doc.path }}</p>
          </div>
          <span>{{ doc.char_count }} chars</span>
        </article>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'

import { runtimeLabel } from '../utils/lotteryDisplay'

const props = defineProps({
  overview: {
    type: Object,
    default: null
  },
  processTrace: {
    type: Array,
    default: () => []
  },
  evaluation: {
    type: Object,
    default: null
  },
  loading: {
    type: Boolean,
    default: false
  }
})

const steps = computed(() => props.processTrace || [])
const documents = computed(() => props.overview?.knowledge_documents || [])
const llmStatus = computed(() => props.overview?.llm_status || null)
const graphSummary = computed(() => props.overview?.workspace_graph || null)
const chartSummary = computed(() => props.overview?.chart_summary || null)
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
.step-head,
.docs-header,
.doc-top {
  display: flex;
  justify-content: space-between;
  gap: 0.8rem;
  align-items: center;
}

.eyebrow,
.panel-meta,
.signal-row span,
.step-head span,
.leader-hint,
.doc-item span,
.doc-item p {
  margin: 0;
  font-size: 0.82rem;
  line-height: 1.6;
  color: var(--lottery-muted, #6e675f);
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0.85rem;
}

.summary-card,
.docs-card,
.doc-item,
.step-card {
  border-radius: 1.15rem;
  border: 1px solid var(--lottery-line, rgba(31, 28, 24, 0.1));
  background: rgba(255, 255, 255, 0.72);
}

.summary-card {
  display: grid;
  gap: 0.35rem;
  padding: 1rem;
}

.summary-card strong {
  font-size: 1.35rem;
}

.signal-row,
.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.55rem;
}

.signal-row span,
.chip {
  padding: 0.36rem 0.75rem;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.75);
}

.chip.solid {
  background: var(--lottery-ink, #1d1b19);
  color: #fff;
}

.step-list,
.docs-list {
  display: grid;
  gap: 0.85rem;
}

.step-card {
  display: grid;
  grid-template-columns: 1rem 1fr;
  gap: 1rem;
  padding: 1rem;
}

.step-dot {
  width: 1rem;
  height: 1rem;
  border-radius: 999px;
  background: rgba(31, 28, 24, 0.12);
}

.step-dot.completed {
  background: var(--lottery-accent, #0f766e);
}

.step-dot.skipped {
  background: rgba(31, 28, 24, 0.24);
}

.step-body {
  display: grid;
  gap: 0.65rem;
}

.step-body p {
  margin: 0;
  line-height: 1.6;
}

.docs-card {
  display: grid;
  gap: 0.85rem;
  padding: 1rem;
}

.doc-item {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.9rem 1rem;
}

.doc-kind {
  display: inline-flex;
  align-items: center;
  padding: 0.25rem 0.7rem;
  border-radius: 999px;
  background: rgba(15, 118, 110, 0.08);
}

@media (max-width: 900px) {
  .summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .summary-grid {
    grid-template-columns: 1fr;
  }

  .doc-item {
    display: grid;
  }
}
</style>
