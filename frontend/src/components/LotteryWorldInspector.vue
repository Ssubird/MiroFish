<template>
  <section class="inspector-shell">
    <header class="inspector-header">
      <div>
        <p class="eyebrow">WORLD</p>
        <h2>持续世界状态</h2>
      </div>
      <div class="header-actions">
        <button type="button" class="ghost-btn" :disabled="busy" @click="$emit('refresh')">刷新</button>
        <button type="button" class="ghost-btn danger" :disabled="busy" @click="$emit('reset')">清空状态</button>
      </div>
    </header>

    <div class="summary-grid">
      <article class="summary-card"><span>状态</span><strong>{{ session?.status || '-' }}</strong></article>
      <article class="summary-card"><span>阶段</span><strong>{{ phaseLabel(session?.current_phase) }}</strong></article>
      <article class="summary-card"><span>目标期</span><strong>{{ session?.current_period || latestPrediction?.period || '-' }}</strong></article>
      <article class="summary-card"><span>模型</span><strong>{{ activeModelName || '-' }}</strong></article>
    </div>

    <article class="section-card focus-card">
      <div class="section-head">
        <h3>选中节点</h3>
        <span>{{ selectedGraphNode?.label || '-' }}</span>
      </div>
      <p v-if="!selectedGraphNode" class="muted">点击左侧世界图节点后，这里会显示摘要、来源和号码。</p>
      <template v-else>
        <div class="chip-row">
          <span class="chip">{{ nodeTypeLabel(selectedGraphNode.node_type) }}</span>
          <span class="chip">{{ nodeScope(selectedGraphNode) }}</span>
        </div>
        <p>{{ selectedGraphNode.summary || selectedGraphNode.comment || selectedGraphNode.meta || '-' }}</p>
        <p class="muted">号码：{{ (selectedGraphNode.numbers || []).join(' / ') || '-' }}</p>
      </template>
    </article>

    <article class="section-card focus-card">
      <div class="section-head">
        <h3>选中号码</h3>
        <span>{{ selectedNumberDetail?.number || '-' }}</span>
      </div>
      <p v-if="!selectedNumberDetail" class="muted">点击下方 1-80 号码板，这里会显示最近 50 期轨迹和讨论提及。</p>
      <template v-else>
        <div class="chip-row">
          <span class="chip">出现 {{ selectedNumberDetail.count }} 次</span>
          <span class="chip">讨论 {{ selectedNumberDetail.mention_count }} 次</span>
        </div>
        <p>最近出现期次：{{ (selectedNumberDetail.periods || []).join(' / ') || '-' }}</p>
        <p class="muted">高频提及：{{ (selectedNumberDetail.mentioned_by || []).join(' / ') || '-' }}</p>
      </template>
    </article>

    <article class="section-card">
      <div class="section-head">
        <h3>当前预测</h3>
        <span>{{ latestPrediction?.period || '-' }}</span>
      </div>
      <div class="chip-row">
        <span v-for="num in latestPrediction?.ensemble_numbers || []" :key="`p-${num}`" class="chip primary">{{ num }}</span>
        <span v-for="num in latestPrediction?.alternate_numbers || []" :key="`a-${num}`" class="chip alt">{{ num }}</span>
      </div>
      <p class="muted">{{ shortText(latestPrediction?.judge_decision?.rationale, 180) || '当前还没有形成最终 5+3。' }}</p>
    </article>

    <div class="stack-grid">
      <article class="section-card compact">
        <div class="section-head">
          <h3>购买方案</h3>
          <span>{{ latestPurchasePlan?.plan_type || latestPurchasePlan?.status || '-' }}</span>
        </div>
        <div class="chip-row">
          <span class="chip">{{ latestPurchasePlan?.play_size ? `选${latestPurchasePlan.play_size}` : '-' }}</span>
          <span class="chip">{{ latestPurchasePlan?.ticket_count || 0 }} 注</span>
          <span class="chip">{{ latestPurchasePlan?.total_cost_yuan || budgetYuan || 0 }} 元</span>
        </div>
        <p>{{ shortText(latestPurchasePlan?.planner?.rationale || latestPurchasePlan?.chosen_edge, 150) || '购买委员会尚未定稿。' }}</p>
      </article>

      <article v-if="latestSettlement" class="section-card compact">
        <div class="section-head">
          <h3>最近结算</h3>
          <span>{{ latestSettlement.period }}</span>
        </div>
        <div class="chip-row">
          <span class="chip">命中 {{ latestSettlement.consensus_hits }}</span>
          <span class="chip">最佳 {{ latestSettlement.best_hits }}</span>
          <span class="chip">盈亏 {{ latestSettlement.purchase_profit }}</span>
        </div>
        <p class="muted">{{ shortText((latestSettlement.actual_numbers || []).join(' / '), 120) }}</p>
      </article>
    </div>

    <article class="section-card">
      <div class="section-head">
        <h3>深度互动</h3>
        <span>{{ liveInterviewEnabled ? '会写入世界时间线' : '当前已关闭' }}</span>
      </div>
      <div class="form-grid">
        <label class="field">
          <span>Agent</span>
          <select :value="agentId" @change="$emit('update:agentId', $event.target.value)">
            <option value="">请选择</option>
            <option v-for="agent in session?.agents || []" :key="agent.session_agent_id" :value="agent.session_agent_id">
              {{ agent.display_name }}
            </option>
          </select>
        </label>
        <label class="field">
          <span>问题</span>
          <textarea
            :value="prompt"
            rows="3"
            placeholder="例如：你为什么保留这个号码？当前最大分歧在哪里？"
            @input="$emit('update:prompt', $event.target.value)"
          />
        </label>
      </div>
      <button
        type="button"
        class="run-btn"
        :disabled="interviewBusy || !liveInterviewEnabled || !agentId || !prompt.trim()"
        @click="$emit('interview')"
      >
        {{ interviewBusy ? '发送中...' : '发送追问' }}
      </button>
    </article>

    <article class="section-card">
      <div class="section-head">
        <h3>最新事件</h3>
        <span>{{ timeline?.total || 0 }}</span>
      </div>
      <div class="event-list">
        <div v-for="event in latestEvents" :key="event.event_id" class="event-item">
          <strong>{{ event.actor_display_name }}</strong>
          <span>{{ eventLabel(event.event_type) }} / {{ phaseLabel(event.phase) }}</span>
          <p>{{ shortText(event.content, 130) }}</p>
        </div>
      </div>
    </article>
  </section>
</template>

<script setup>
import { computed } from 'vue'

import { eventLabel, groupLabel, nodeTypeLabel, phaseLabel, shortText } from '../utils/lotteryDisplay'

const props = defineProps({
  sessionData: { type: Object, default: null },
  latestPrediction: { type: Object, default: null },
  latestPurchasePlan: { type: Object, default: null },
  latestSettlement: { type: Object, default: null },
  selectedGraphNode: { type: Object, default: null },
  selectedNumberDetail: { type: Object, default: null },
  timeline: { type: Object, default: () => ({ items: [], total: 0 }) },
  budgetYuan: { type: Number, default: 50 },
  activeModelName: { type: String, default: '' },
  busy: { type: Boolean, default: false },
  interviewBusy: { type: Boolean, default: false },
  liveInterviewEnabled: { type: Boolean, default: true },
  agentId: { type: String, default: '' },
  prompt: { type: String, default: '' }
})

defineEmits(['refresh', 'reset', 'interview', 'update:agentId', 'update:prompt'])

const session = computed(() => props.sessionData?.session || null)
const latestEvents = computed(() => (props.timeline?.items || []).slice(0, 8))

const nodeScope = (node) => {
  if (!node) return '-'
  if (node.node_type === 'phase' || node.node_type === 'debate_round') return phaseLabel(node.phase)
  return groupLabel(node.group || '-')
}
</script>

<style scoped>
.inspector-shell { display: flex; flex-direction: column; gap: 0.95rem; min-width: 0; max-height: calc(100vh - 2rem); overflow: auto; padding: 1.1rem; border-radius: 1.5rem; border: 1px solid rgba(31, 28, 24, 0.1); background: rgba(255, 251, 244, 0.92); box-shadow: 0 18px 42px rgba(29, 27, 25, 0.08); }
.summary-grid, .stack-grid, .event-list, .form-grid { display: grid; gap: 0.9rem; }
.summary-grid, .stack-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.inspector-header, .header-actions, .section-head, .chip-row { display: flex; align-items: center; gap: 0.65rem; flex-wrap: wrap; }
.inspector-header, .section-head { justify-content: space-between; }
.summary-card, .section-card, .event-item { display: grid; gap: 0.6rem; align-content: start; min-width: 0; padding: 0.95rem; border-radius: 1rem; border: 1px solid rgba(31, 28, 24, 0.1); background: rgba(255, 255, 255, 0.9); }
.focus-card { min-height: 8rem; }
.summary-card strong, .summary-card span, .section-card p, .event-item p, .event-item span, .section-head span, .muted { overflow-wrap: anywhere; word-break: break-word; }
.summary-card strong, .summary-card span, .section-card p, .event-item p, .event-item span, .eyebrow, .section-head h3, .inspector-header h2 { margin: 0; }
.section-head span { max-width: 100%; color: #6e675f; text-align: right; }
.chip-row { justify-content: flex-start; }
.chip { display: inline-flex; align-items: center; padding: 0.24rem 0.7rem; border-radius: 999px; border: 1px solid rgba(31, 28, 24, 0.12); background: rgba(246, 243, 236, 0.95); }
.chip.primary, .chip.alt { background: #1d1b19; color: #fff; }
.ghost-btn, .run-btn, select, textarea { font: inherit; }
.ghost-btn, .run-btn { border: 1px solid rgba(31, 28, 24, 0.14); border-radius: 999px; padding: 0.56rem 0.95rem; background: rgba(255, 255, 255, 0.9); cursor: pointer; }
.ghost-btn.danger { color: #8f3434; }
.run-btn { background: #1d1b19; color: #fff; }
.field, .form-grid { display: grid; gap: 0.45rem; }
.field select, .field textarea { width: 100%; border-radius: 0.95rem; border: 1px solid rgba(31, 28, 24, 0.14); padding: 0.8rem 0.9rem; background: rgba(255, 255, 255, 0.94); }
.event-list { max-height: 16rem; overflow: auto; }
.eyebrow, .muted, .summary-card span, .event-item span { color: #6e675f; }
@media (max-width: 960px) { .inspector-shell { max-height: none; overflow: visible; } .summary-grid, .stack-grid { grid-template-columns: 1fr; } }
</style>
