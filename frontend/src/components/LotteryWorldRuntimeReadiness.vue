<template>
  <article class="readiness-card" :class="{ ready: readiness?.ready }">
    <div class="readiness-head">
      <div>
        <span class="eyebrow">READINESS</span>
        <strong>运行前置条件</strong>
      </div>
      <span class="state-pill">{{ stateLabel }}</span>
    </div>

    <p v-if="loading" class="summary">正在检查 Letta / MCP readiness...</p>
    <template v-else>
      <p class="summary">{{ summary }}</p>
      <p v-if="readiness?.blocking_code" class="code-line">
        阻塞码：<code>{{ readiness.blocking_code }}</code>
      </p>

      <ul v-if="detailItems.length" class="detail-list">
        <li v-for="item in detailItems" :key="item">{{ item }}</li>
      </ul>

      <div class="source-grid">
        <div class="source-card">
          <strong><code>LLM_BASE_URL</code></strong>
          <span>只负责模型列表与测试模型</span>
        </div>
        <div class="source-card">
          <strong><code>LETTA_BASE_URL</code></strong>
          <span>只负责 Letta agent / memory / MCP orchestration</span>
        </div>
      </div>

      <p v-if="readiness?.letta?.base_url" class="base-url">
        当前 Letta 地址：<code>{{ readiness.letta.base_url }}</code>
      </p>
    </template>
  </article>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  readiness: { type: Object, default: null },
  loading: { type: Boolean, default: false }
})

const stateLabel = computed(() => {
  if (props.loading) return '检查中'
  if (props.readiness?.runtime_backend === 'local_no_mcp') return '已就绪 / 无 MCP'
  return props.readiness?.ready ? '已就绪' : '未就绪'
})

const summary = computed(() => {
  if (props.loading) return ''
  if (props.readiness?.summary) return props.readiness.summary
  if (props.readiness?.ready) return '当前 world_v2_market 已满足运行前置条件。'
  return props.readiness?.blocking_message || '当前 world_v2_market 还不能启动。'
})

const detailItems = computed(() => {
  const items = props.readiness?.details
  return Array.isArray(items) ? items.filter(Boolean) : []
})
</script>

<style scoped>
.readiness-card,
.source-grid {
  display: grid;
  gap: 0.9rem;
}

.readiness-card {
  padding: 1rem;
  border-radius: 1rem;
  border: 1px solid rgba(255, 110, 110, 0.24);
  background: rgba(255, 80, 80, 0.08);
}

.readiness-card.ready {
  border-color: rgba(0, 240, 255, 0.22);
  background: rgba(0, 240, 255, 0.06);
}

.readiness-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}

.state-pill,
.source-card,
.code-line code,
.base-url code {
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(0, 0, 0, 0.25);
}

.state-pill {
  padding: 0.35rem 0.8rem;
  color: #fff;
  font-size: 0.82rem;
}

.summary,
.code-line,
.detail-list,
.base-url,
.source-card span,
.eyebrow {
  margin: 0;
  color: #a9b7c6;
}

.code-line code,
.base-url code {
  padding: 0.15rem 0.4rem;
  font-family: 'JetBrains Mono', monospace;
}

.detail-list {
  padding-left: 1.1rem;
}

.source-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.source-card {
  display: grid;
  gap: 0.35rem;
  padding: 0.85rem;
}

@media (max-width: 720px) {
  .source-grid {
    grid-template-columns: 1fr;
  }
}
</style>
