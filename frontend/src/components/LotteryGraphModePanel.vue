<template>
  <section class="panel">
    <div class="panel-head">
      <div>
        <p class="eyebrow">GRAPH SOURCE</p>
        <h2>图谱来源</h2>
      </div>
      <span class="mode-pill" :class="mode">{{ activeLabel }}</span>
    </div>

    <div class="mode-grid">
      <button class="mode-card" :class="{ active: mode === 'local' }" @click="$emit('update:mode', 'local')">
        <strong>本地快照</strong>
        <span>直接使用工作区内存快照，最快，不需要额外同步。</span>
      </button>
      <button class="mode-card" :class="{ active: mode === 'kuzu' }" @click="$emit('update:mode', 'kuzu')">
        <strong>Kuzu 本地图谱</strong>
        <span>把书、命盘、开奖写入本地图数据库，再从图里检索上下文。</span>
      </button>
      <button class="mode-card" :class="{ active: mode === 'zep' }" @click="$emit('update:mode', 'zep')">
        <strong>Zep 远程图谱</strong>
        <span>使用远程记忆图谱检索，会消耗 Zep 配额。</span>
      </button>
    </div>

    <div class="status-grid">
      <article class="status-card">
        <span>当前状态</span>
        <strong>{{ activeStatus?.available ? '可用' : mode === 'local' ? '始终可用' : '未同步' }}</strong>
      </article>
      <article class="status-card">
        <span>节点 / 关系</span>
        <strong>{{ `${activeStatus?.node_count || 0} / ${activeStatus?.edge_count || 0}` }}</strong>
      </article>
      <article class="status-card">
        <span>图谱 ID</span>
        <strong>{{ activeStatus?.graph_id || 'memory-only' }}</strong>
      </article>
      <article class="status-card">
        <span>同步状态</span>
        <strong>{{ activeStatus?.is_stale ? '需要重建' : '已对齐' }}</strong>
      </article>
    </div>

    <div class="detail-card">
      <p v-if="mode === 'local'">本轮回测会使用本地快照，不会访问远程图谱，也不需要本地数据库同步。</p>
      <p v-else-if="mode === 'kuzu'">Kuzu 会把紫微书、命盘、开奖持久化到本地图库。回测阶段只读取当前可见期数，不会把未来开奖混进去。</p>
      <p v-else>当前是 Zep 模式。只有同步成功后，回测才会真正读取远程图谱，而不是本地快照。</p>
      <p v-if="activeStatus?.db_path">DB: <code>{{ activeStatus.db_path }}</code></p>
      <p v-if="activeStatus?.synced_at">最近同步：{{ activeStatus.synced_at }}</p>
    </div>

    <div v-if="mode !== 'local'" class="action-row">
      <button class="sync-btn" :disabled="syncing || syncBlocked" @click="$emit('sync', false)">
        {{ syncing ? '同步中...' : `同步到 ${activeLabel}` }}
      </button>
      <button class="ghost-btn" :disabled="syncing || syncBlocked" @click="$emit('sync', true)">
        强制重建
      </button>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  mode: { type: String, default: 'local' },
  statuses: { type: Object, default: () => ({}) },
  syncing: { type: Boolean, default: false }
})

defineEmits(['update:mode', 'sync'])

const labelMap = { local: 'Local', kuzu: 'Kuzu', zep: 'Zep' }
const activeLabel = computed(() => labelMap[props.mode] || 'Local')
const activeStatus = computed(() => props.statuses?.[props.mode] || null)
const syncBlocked = computed(() => props.mode === 'zep' && !props.statuses?.zep?.configured)
</script>

<style scoped>
.panel,
.status-grid,
.mode-grid {
  display: grid;
  gap: 1rem;
}

.panel {
  padding: 1.35rem;
  border-radius: 1.5rem;
  border: 1px solid var(--lottery-line, rgba(31, 28, 24, 0.1));
  background: var(--lottery-panel, rgba(255, 251, 244, 0.92));
  box-shadow: var(--lottery-shadow, 0 18px 40px rgba(24, 22, 19, 0.08));
}

.panel-head,
.action-row {
  display: flex;
  justify-content: space-between;
  gap: 0.8rem;
  align-items: center;
}

.eyebrow,
.detail-card p,
.mode-card span,
.status-card span {
  margin: 0;
  font-size: 0.82rem;
  line-height: 1.6;
  color: var(--lottery-muted, #6e675f);
}

.mode-pill,
.status-card strong {
  color: var(--lottery-ink, #1d1b19);
}

.mode-pill {
  padding: 0.45rem 0.8rem;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.76);
}

.mode-pill.kuzu {
  background: rgba(183, 121, 31, 0.14);
}

.mode-pill.zep {
  background: rgba(15, 118, 110, 0.12);
}

.mode-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.status-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.mode-card,
.status-card,
.detail-card {
  display: grid;
  gap: 0.35rem;
  padding: 1rem;
  border-radius: 1.15rem;
  border: 1px solid var(--lottery-line, rgba(31, 28, 24, 0.1));
  background: rgba(255, 255, 255, 0.72);
}

.mode-card {
  text-align: left;
  cursor: pointer;
  font: inherit;
}

.mode-card.active {
  border-color: rgba(15, 118, 110, 0.24);
  background: rgba(15, 118, 110, 0.08);
}

.sync-btn,
.ghost-btn {
  border: 1px solid var(--lottery-line-strong, rgba(31, 28, 24, 0.16));
  border-radius: 999px;
  padding: 0.78rem 1rem;
  font: inherit;
  cursor: pointer;
}

.sync-btn {
  background: var(--lottery-ink, #1d1b19);
  color: #fff;
}

.ghost-btn {
  background: rgba(255, 255, 255, 0.82);
}

.sync-btn:disabled,
.ghost-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

@media (max-width: 900px) {
  .mode-grid,
  .status-grid {
    grid-template-columns: 1fr;
  }
}
</style>
