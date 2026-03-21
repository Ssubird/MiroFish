<template>
  <section class="control-shell">
    <header class="control-header">
      <div class="title-block">
        <p class="eyebrow">COMMAND CENTER</p>
        <h2>世界推进控制台</h2>
        <p class="subtitle">按可见截止期推进 `world_v2_market`，并为当前 session 调整执行绑定。</p>
      </div>
      <button type="button" class="run-btn" :disabled="!canAdvance" @click="$emit('advance')">
        {{ running ? '运行中…' : '推进一轮' }}
      </button>
    </header>

    <p v-if="runMessage" class="run-banner">{{ runMessage }}</p>

    <div class="summary-grid">
      <article class="summary-card">
        <span>预算</span>
        <strong>{{ budgetYuan }} 元</strong>
      </article>
      <article class="summary-card">
        <span>并发</span>
        <strong>x{{ llmParallelism }}</strong>
      </article>
      <article class="summary-card">
        <span>讨论轮数</span>
        <strong>{{ agentDialogueRounds }}</strong>
      </article>
      <article class="summary-card">
        <span>已选 agent</span>
        <strong>{{ selectedIds.length }}</strong>
      </article>
    </div>

    <details class="fold-panel" open>
      <summary class="fold-summary">
        <span>运行条件</span>
        <small :class="{ ready: runtimeReadiness?.ready }">
          {{ runtimeReadiness?.ready ? '已就绪' : '待检查' }}
        </small>
      </summary>
      <div class="fold-body">
        <LotteryWorldRuntimeReadiness
          :readiness="runtimeReadiness"
          :loading="runtimeReadinessLoading"
        />

        <div class="inline-card">
          <div>
            <strong>Kuzu 图谱</strong>
            <p class="muted">
              {{ kuzuStateLabel }} / {{ kuzuFreshnessLabel }} / 节点 {{ kuzuGraphStatus?.node_count ?? 0 }} / 关系
              {{ kuzuGraphStatus?.edge_count ?? 0 }}
            </p>
          </div>
          <button type="button" class="ghost-btn" :disabled="graphSyncing" @click="$emit('sync-kuzu')">
            {{ graphSyncing ? '同步中…' : '同步 Kuzu' }}
          </button>
        </div>
      </div>
    </details>

    <details class="fold-panel" open>
      <summary class="fold-summary">
        <span>参数配置</span>
        <small>{{ fieldCount }} 项</small>
      </summary>
      <div class="fold-body">
        <div class="field-grid">
          <label class="field">
            <span>购买预算</span>
            <input
              :value="budgetYuan"
              type="number"
              min="2"
              max="500"
              step="2"
              @input="$emit('update:budgetYuan', Number($event.target.value || 0))"
            />
          </label>

          <label class="field">
            <span>LLM 并行数</span>
            <input
              :value="llmParallelism"
              type="number"
              min="1"
              max="32"
              @input="$emit('update:llmParallelism', Number($event.target.value || 1))"
            />
          </label>

          <label class="field">
            <span>讨论轮数</span>
            <input
              :value="agentDialogueRounds"
              type="number"
              min="0"
              max="5"
              @input="$emit('update:agentDialogueRounds', Number($event.target.value || 0))"
            />
          </label>

          <label class="field">
            <span>可见截止期</span>
            <select :value="visibleThroughPeriod" @change="$emit('update:visibleThroughPeriod', $event.target.value)">
              <option value="">使用当前最新已开奖期</option>
              <option v-for="period in historyPeriods" :key="period" :value="period">
                {{ period }}
              </option>
            </select>
        </label>
      </div>

      <label class="toggle-field">
        <input
          :checked="startNewSession"
          type="checkbox"
          @change="$emit('update:startNewSession', $event.target.checked)"
        />
        <span>本次强制新建会话，不续跑当前 session</span>
      </label>

      <label class="toggle-field">
          <input
            :checked="liveInterviewEnabled"
            type="checkbox"
            @change="$emit('update:liveInterviewEnabled', $event.target.checked)"
          />
          <span>运行时启用人工追问并写入时间线</span>
        </label>
      </div>
    </details>

    <details class="fold-panel" :open="hasMultiProvider">
      <summary class="fold-summary">
        <span>模型与 Provider</span>
        <small>{{ selectedModelName || '默认模型' }}</small>
      </summary>
      <div class="fold-body">
        <div v-if="hasMultiProvider" class="provider-note">
          <strong>已检测到多供应商执行配置</strong>
          <p class="muted">
            当前 world_v2 多供应商模式以 `profile_id` 绑定执行。原始模型列表只覆盖默认 provider，请优先使用下方
            `Execution Bindings` 选择 profile。
          </p>
          <div class="pill-row">
            <span v-for="provider in catalogProviders" :key="provider.provider_id" class="pill">
              {{ provider.provider_id }}
            </span>
          </div>
        </div>

        <label class="field">
          <div class="field-head">
            <span>默认模型</span>
            <div class="model-actions">
              <button type="button" class="ghost-btn" :disabled="llmModelLoading" @click="$emit('load-models')">
                {{ llmModelLoading ? '读取中…' : '读取列表' }}
              </button>
              <button
                type="button"
                class="ghost-btn"
                :disabled="llmModelLoading || hasMultiProvider"
                @click="$emit('probe-model')"
              >
                测试
              </button>
            </div>
          </div>
          <select :value="selectedModelName" @change="$emit('update:selectedModelName', $event.target.value)">
            <option v-for="model in modelOptions" :key="model.id" :value="model.id">
              {{ model.label }}
            </option>
          </select>
        </label>

        <p v-if="modelListStatus" class="muted">{{ modelListStatus }}</p>
        <p v-if="modelProbeResult" class="muted">{{ modelProbeResult.message }}</p>

        <div v-if="catalogProfiles.length" class="profile-preview">
          <span v-for="profile in catalogProfiles.slice(0, 8)" :key="profile.profile_id" class="profile-chip">
            {{ profileLabel(profile) }}
          </span>
        </div>
      </div>
    </details>

    <details class="fold-panel" :open="hasMultiProvider">
      <summary class="fold-summary">
        <span>Execution Bindings</span>
        <small>{{ catalogProviders.length }} provider / {{ catalogProfiles.length }} profile</small>
      </summary>
      <div class="fold-body">
        <LotteryExecutionBindingsPanel
          :catalog="executionCatalog"
          :overrides="executionOverrides"
          :bindings="resolvedExecutionBindings"
          :agents="sessionAgents"
          @update-binding="$emit('update:executionBinding', $event)"
          @reset="$emit('reset:executionBindings')"
        />
      </div>
    </details>

    <details class="fold-panel" open>
      <summary class="fold-summary">
        <span>Agent 选择</span>
        <small>{{ selectedIds.length }} 已选</small>
      </summary>
      <div class="fold-body">
        <div class="field-head">
          <span class="muted">本轮将推进这些生成策略</span>
          <button type="button" class="ghost-btn" @click="$emit('select-all')">全选</button>
        </div>
        <div class="strategy-grid">
          <label v-for="strategy in strategies" :key="strategy.strategy_id" class="strategy-card">
            <input
              :checked="selectedIds.includes(strategy.strategy_id)"
              type="checkbox"
              @change="$emit('toggle-strategy', strategy.strategy_id)"
            />
            <div class="strategy-copy">
              <strong>{{ strategy.display_name }}</strong>
              <p>{{ groupLabel(strategy.group) }} / {{ kindLabel(strategy.kind) }}</p>
            </div>
          </label>
        </div>
      </div>
    </details>
  </section>
</template>

<script setup>
import { computed } from 'vue'

import LotteryExecutionBindingsPanel from './LotteryExecutionBindingsPanel.vue'
import LotteryWorldRuntimeReadiness from './LotteryWorldRuntimeReadiness.vue'
import { groupLabel, kindLabel } from '../utils/lotteryDisplay'

const FIELD_COUNT = 6

const props = defineProps({
  strategies: { type: Array, default: () => [] },
  selectedIds: { type: Array, default: () => [] },
  budgetYuan: { type: Number, default: 50 },
  llmParallelism: { type: Number, default: 8 },
  agentDialogueRounds: { type: Number, default: 1 },
  startNewSession: { type: Boolean, default: false },
  liveInterviewEnabled: { type: Boolean, default: true },
  llmModels: { type: Array, default: () => [] },
  selectedModelName: { type: String, default: '' },
  modelProbeResult: { type: Object, default: null },
  modelListStatus: { type: String, default: '' },
  llmModelLoading: { type: Boolean, default: false },
  executionCatalog: { type: Object, default: null },
  executionOverrides: { type: Object, default: () => ({ group_overrides: {}, agent_overrides: {} }) },
  resolvedExecutionBindings: { type: Object, default: () => ({}) },
  sessionAgents: { type: Array, default: () => [] },
  runtimeReadiness: { type: Object, default: null },
  runtimeReadinessLoading: { type: Boolean, default: false },
  graphSyncing: { type: Boolean, default: false },
  kuzuGraphStatus: { type: Object, default: () => ({}) },
  runMessage: { type: String, default: '' },
  busy: { type: Boolean, default: false },
  running: { type: Boolean, default: false },
  canAdvance: { type: Boolean, default: false },
  visibleThroughPeriod: { type: String, default: '' },
  historyPeriods: { type: Array, default: () => [] }
})

defineEmits([
  'advance',
  'sync-kuzu',
  'probe-model',
  'load-models',
  'select-all',
  'toggle-strategy',
  'update:budgetYuan',
  'update:llmParallelism',
  'update:agentDialogueRounds',
  'update:startNewSession',
  'update:liveInterviewEnabled',
  'update:selectedModelName',
  'update:visibleThroughPeriod',
  'update:executionBinding',
  'reset:executionBindings'
])

const fieldCount = FIELD_COUNT

const modelOptions = computed(() => {
  const options = []
  const seen = new Set()
  const pushOption = (id, label) => {
    if (!id || seen.has(id)) return
    seen.add(id)
    options.push({ id, label })
  }

  pushOption(props.selectedModelName, props.selectedModelName)
  props.llmModels.forEach((model) => {
    const id = model.id || model.name || ''
    const label = model.label || id
    pushOption(id, label)
  })

  if (!options.length) {
    options.push({ id: '', label: '使用 .env 默认模型' })
  }
  return options
})

const catalogProviders = computed(() => props.executionCatalog?.providers || [])
const catalogProfiles = computed(() => props.executionCatalog?.profiles || [])
const hasMultiProvider = computed(() => {
  const ids = new Set(catalogProviders.value.map((item) => item.provider_id).filter(Boolean))
  return ids.size > 1
})

const profileLabel = (profile) => {
  const provider = profile.provider_id || '-'
  const model = profile.model_id || '-'
  return `${profile.profile_id} · ${provider} / ${model}`
}

const kuzuStateLabel = computed(() => (
  props.kuzuGraphStatus?.available ? '已同步' : '未同步'
))

const kuzuFreshnessLabel = computed(() => (
  props.kuzuGraphStatus?.is_stale ? '需要刷新' : '最新'
))
</script>

<style scoped>
.control-shell {
  display: grid;
  gap: 1rem;
  padding: 1.35rem;
  border-radius: 1.5rem;
  border: 1px solid var(--lottery-line, rgba(31, 28, 24, 0.1));
  background: var(--lottery-panel, rgba(255, 251, 244, 0.92));
  box-shadow: var(--lottery-shadow, 0 18px 40px rgba(24, 22, 19, 0.08));
  color: var(--lottery-ink, #1d1b19);
}

.control-header,
.field-head,
.model-actions,
.inline-card {
  display: flex;
  gap: 0.8rem;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
}

.title-block,
.summary-grid,
.field-grid,
.fold-body,
.strategy-grid,
.pill-row,
.profile-preview {
  display: grid;
  gap: 0.85rem;
}

.title-block {
  min-width: 0;
}

.eyebrow,
.subtitle,
.muted,
.summary-card span,
.fold-summary small {
  margin: 0;
  color: var(--lottery-muted, #6e675f);
  line-height: 1.6;
}

.control-header h2 {
  margin: 0;
  font-size: 1.5rem;
}

.run-btn,
.ghost-btn {
  border-radius: 999px;
  padding: 0.72rem 1rem;
  font: inherit;
  cursor: pointer;
  transition: transform 0.18s ease, box-shadow 0.18s ease, background 0.18s ease;
}

.run-btn {
  border: 1px solid var(--lottery-ink, #1d1b19);
  background: var(--lottery-ink, #1d1b19);
  color: #fff;
}

.ghost-btn {
  border: 1px solid var(--lottery-line-strong, rgba(31, 28, 24, 0.16));
  background: rgba(255, 255, 255, 0.78);
  color: inherit;
}

.run-btn:hover:not(:disabled),
.ghost-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 10px 24px rgba(24, 22, 19, 0.08);
}

.run-btn:disabled,
.ghost-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
  transform: none;
  box-shadow: none;
}

.run-banner,
.inline-card,
.provider-note,
.summary-card,
.strategy-card {
  border-radius: 1.1rem;
  border: 1px solid var(--lottery-line, rgba(31, 28, 24, 0.1));
  background: rgba(255, 255, 255, 0.72);
}

.run-banner,
.inline-card,
.provider-note,
.summary-card {
  padding: 0.95rem 1rem;
}

.run-banner {
  margin: 0;
  background: rgba(15, 118, 110, 0.08);
}

.summary-grid,
.field-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.summary-card strong {
  display: block;
  margin-top: 0.25rem;
  font-size: 1.1rem;
}

.fold-panel {
  border-radius: 1.3rem;
  border: 1px solid var(--lottery-line, rgba(31, 28, 24, 0.1));
  background: rgba(255, 250, 243, 0.88);
  overflow: hidden;
}

.fold-summary {
  display: flex;
  justify-content: space-between;
  gap: 0.8rem;
  align-items: center;
  padding: 1rem 1.1rem;
  cursor: pointer;
  list-style: none;
  font-weight: 700;
}

.fold-summary::-webkit-details-marker {
  display: none;
}

.fold-summary small.ready {
  color: #0f766e;
}

.fold-body {
  padding: 0 1rem 1rem;
}

.field {
  display: grid;
  gap: 0.45rem;
  min-width: 0;
}

.field input,
.field select {
  width: 100%;
  min-width: 0;
  border-radius: 1rem;
  border: 1px solid var(--lottery-line-strong, rgba(31, 28, 24, 0.16));
  padding: 0.88rem 0.95rem;
  background: rgba(255, 255, 255, 0.9);
  font: inherit;
}

.field input:focus,
.field select:focus {
  outline: none;
  border-color: rgba(15, 118, 110, 0.4);
  box-shadow: 0 0 0 3px rgba(15, 118, 110, 0.08);
}

.toggle-field {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 0.65rem;
  align-items: center;
}

.toggle-field input[type='checkbox'] {
  width: 1rem;
  height: 1rem;
  accent-color: #0f766e;
}

.pill-row,
.profile-preview {
  grid-template-columns: repeat(auto-fit, minmax(8rem, 1fr));
}

.pill,
.profile-chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 2.2rem;
  padding: 0.4rem 0.75rem;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.88);
  border: 1px solid var(--lottery-line, rgba(31, 28, 24, 0.1));
  font-size: 0.82rem;
  text-align: center;
  overflow-wrap: anywhere;
}

.strategy-grid {
  max-height: 24rem;
  overflow: auto;
  padding-right: 0.25rem;
}

.strategy-card {
  display: flex;
  gap: 0.75rem;
  align-items: flex-start;
  padding: 0.85rem 0.95rem;
  cursor: pointer;
}

.strategy-card input[type='checkbox'] {
  margin-top: 0.15rem;
  accent-color: #0f766e;
}

.strategy-copy {
  min-width: 0;
}

.strategy-copy strong,
.strategy-copy p,
.provider-note strong {
  margin: 0;
  overflow-wrap: anywhere;
}

@media (max-width: 860px) {
  .summary-grid,
  .field-grid {
    grid-template-columns: 1fr;
  }
}
</style>
