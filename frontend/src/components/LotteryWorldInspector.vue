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

    <article class="section-card focus-card" :class="{ 'is-active': selectedGraphNode }">
      <div class="section-head">
        <h3>选中节点</h3>
        <span>{{ selectedGraphNode?.label || '-' }}</span>
      </div>
      <p v-if="!selectedGraphNode" class="muted">点击左侧图表节点后，此处将自动显示节点详情。</p>
      <template v-else>
        <div class="chip-row">
          <span class="chip">{{ nodeTypeLabel(selectedGraphNode.node_type) }}</span>
          <span class="chip">{{ nodeScope(selectedGraphNode) }}</span>
        </div>
        <div class="focus-content">
          <p>{{ selectedGraphNode.summary || selectedGraphNode.comment || selectedGraphNode.meta || '-' }}</p>
          <div class="focus-meta">号码：{{ (selectedGraphNode.numbers || []).join(' / ') || '-' }}</div>
        </div>
      </template>
    </article>

    <article class="section-card focus-card" :class="{ 'is-active': selectedNumberDetail }">
      <div class="section-head">
        <h3>选中号码</h3>
        <span>{{ selectedNumberDetail?.number || '-' }}</span>
      </div>
      <p v-if="!selectedNumberDetail" class="muted">点击底部 1-80 号码板，此处将显示最近轨迹。</p>
      <template v-else>
        <div class="chip-row">
          <span class="chip">出现 {{ selectedNumberDetail.count }} 次</span>
          <span class="chip">讨论 {{ selectedNumberDetail.mention_count }} 次</span>
        </div>
        <div class="focus-content">
          <p>最近出现期次：{{ (selectedNumberDetail.periods || []).join(' / ') || '-' }}</p>
          <div class="focus-meta">高频提及：{{ (selectedNumberDetail.mentioned_by || []).join(' / ') || '-' }}</div>
        </div>
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
.inspector-shell {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  min-width: 0;
  max-height: calc(100vh - 2.7rem);
  overflow: auto;
  padding: 1.25rem;
  border-radius: 1.5rem;
  border: 1px solid rgba(0, 240, 255, 0.15);
  background: rgba(11, 12, 16, 0.6);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  box-shadow: 0 20px 48px rgba(0, 0, 0, 0.5), inset 0 0 20px rgba(0, 240, 255, 0.05);
  color: #e0e6ed;
}

/* Custom Scrollbar */
.inspector-shell::-webkit-scrollbar {
  width: 6px;
}
.inspector-shell::-webkit-scrollbar-track {
  background: rgba(255, 255, 255, 0.02);
  border-radius: 10px;
}
.inspector-shell::-webkit-scrollbar-thumb {
  background: rgba(0, 240, 255, 0.2);
  border-radius: 10px;
}
.inspector-shell::-webkit-scrollbar-thumb:hover {
  background: rgba(0, 240, 255, 0.4);
}

.summary-grid,
.stack-grid,
.event-list,
.form-grid {
  display: grid;
  gap: 1rem;
  flex-shrink: 0;
}

.summary-grid,
.stack-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.inspector-header,
.header-actions,
.section-head,
.chip-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.inspector-header {
  flex-shrink: 0;
}

.inspector-header,
.section-head {
  justify-content: space-between;
}

.summary-card,
.section-card,
.event-item {
  display: grid;
  gap: 0.75rem;
  align-content: start;
  min-width: 0;
  padding: 1rem;
  border-radius: 1rem;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.03);
  transition: all 0.3s ease;
  flex-shrink: 0;
}

.focus-card {
  min-height: 8rem;
  border-color: rgba(0, 240, 255, 0.2);
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.03) 0%, rgba(0, 240, 255, 0.05) 100%);
  box-shadow: inset 0 0 15px rgba(0, 240, 255, 0.05);
  transition: all 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275);
}

.focus-card.is-active {
  border-color: #00f0ff;
  box-shadow: 0 0 20px rgba(0, 240, 255, 0.3), inset 0 0 20px rgba(0, 240, 255, 0.2);
  background: rgba(0, 240, 255, 0.08);
  transform: translateY(-2px);
}

.focus-card.is-active .section-head h3 {
  color: #00f0ff;
  text-shadow: 0 0 10px rgba(0, 240, 255, 0.5);
}

.focus-content {
  background: rgba(0, 0, 0, 0.4);
  padding: 0.85rem;
  border-radius: 0.75rem;
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.focus-content p {
  line-height: 1.6;
  color: #fff;
  font-size: 0.95rem;
}

.focus-meta {
  margin-top: 0.75rem;
  padding-top: 0.75rem;
  border-top: 1px dashed rgba(255, 255, 255, 0.1);
  color: #00f0ff;
  font-family: monospace;
  font-size: 0.95rem;
}

.summary-card:hover,
.section-card:hover,
.event-item:hover {
  background: rgba(255, 255, 255, 0.06);
  border-color: rgba(0, 240, 255, 0.2);
}

.summary-card strong,
.summary-card span,
.section-card p,
.event-item p,
.event-item span,
.section-head span,
.muted {
  overflow-wrap: anywhere;
  word-break: break-word;
}

.summary-card strong,
.summary-card span,
.section-card p,
.event-item p,
.event-item span,
.eyebrow,
.section-head h3,
.inspector-header h2 {
  margin: 0;
}

.summary-card strong {
  display: block;
  font-size: 1.15rem;
  color: #fff;
  margin-top: 0.25rem;
}

.section-head h3 {
  font-size: 1.1rem;
  font-weight: 600;
  color: #fff;
}

.section-head span {
  max-width: 100%;
  color: #00f0ff;
  text-align: right;
  font-size: 0.9rem;
  font-weight: 600;
}

.chip-row {
  justify-content: flex-start;
}

.chip {
  display: inline-flex;
  align-items: center;
  padding: 0.25rem 0.75rem;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.15);
  background: rgba(255, 255, 255, 0.05);
  font-size: 0.85rem;
  font-weight: 500;
  color: #e0e6ed;
}

.chip.primary {
  background: rgba(0, 240, 255, 0.15);
  border-color: rgba(0, 240, 255, 0.4);
  color: #00f0ff;
  box-shadow: 0 0 10px rgba(0, 240, 255, 0.2);
}

.chip.alt {
  background: rgba(176, 32, 240, 0.15);
  border-color: rgba(176, 32, 240, 0.4);
  color: #e0a3ff;
  box-shadow: 0 0 10px rgba(176, 32, 240, 0.2);
}

.ghost-btn,
.run-btn,
select,
textarea {
  font: inherit;
}

.ghost-btn,
.run-btn {
  border-radius: 999px;
  padding: 0.5rem 1rem;
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
  font-weight: 600;
  font-size: 0.9rem;
}

.ghost-btn {
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(255, 255, 255, 0.05);
  color: #a0b2c6;
}

.ghost-btn:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.1);
  color: #fff;
}

.ghost-btn.danger {
  color: #ff6b6b;
  border-color: rgba(255, 107, 107, 0.3);
  background: rgba(255, 107, 107, 0.1);
}

.ghost-btn.danger:hover:not(:disabled) {
  background: rgba(255, 107, 107, 0.2);
  color: #ff8c8c;
  box-shadow: 0 0 15px rgba(255, 107, 107, 0.2);
}

.run-btn {
  border: 1px solid rgba(0, 240, 255, 0.4);
  background: rgba(0, 240, 255, 0.1);
  color: #00f0ff;
  box-shadow: 0 0 15px rgba(0, 240, 255, 0.2), inset 0 0 10px rgba(0, 240, 255, 0.1);
}

.run-btn:hover:not(:disabled) {
  background: rgba(0, 240, 255, 0.2);
  box-shadow: 0 0 25px rgba(0, 240, 255, 0.4), inset 0 0 20px rgba(0, 240, 255, 0.2);
  transform: translateY(-2px);
  color: #fff;
}

.run-btn:disabled,
.ghost-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.field,
.form-grid {
  display: grid;
  gap: 0.5rem;
}

.field select,
.field textarea {
  width: 100%;
  border-radius: 0.75rem;
  border: 1px solid rgba(255, 255, 255, 0.1);
  padding: 0.85rem 1rem;
  background: rgba(0, 0, 0, 0.3);
  color: #fff;
  transition: all 0.3s ease;
  resize: vertical;
}

.field select:focus,
.field textarea:focus {
  outline: none;
  border-color: rgba(0, 240, 255, 0.5);
  box-shadow: 0 0 10px rgba(0, 240, 255, 0.2);
  background: rgba(0, 0, 0, 0.5);
}

.event-list {
  max-height: 18rem;
  overflow: auto;
  padding-right: 0.5rem;
}

.event-list::-webkit-scrollbar {
  width: 6px;
}
.event-list::-webkit-scrollbar-track {
  background: rgba(255, 255, 255, 0.02);
  border-radius: 10px;
}
.event-list::-webkit-scrollbar-thumb {
  background: rgba(0, 240, 255, 0.2);
  border-radius: 10px;
}

.event-item strong {
  color: #00f0ff;
  font-size: 1.05rem;
}

.event-item span {
  font-size: 0.85rem;
  color: #8b9bb4;
}

.event-item p {
  color: #e0e6ed;
  line-height: 1.5;
}

.eyebrow,
.muted,
.summary-card span,
.event-item span {
  color: #8b9bb4;
}

.inspector-header h2 {
  font-size: 1.5rem;
  font-weight: 700;
  color: #fff;
  letter-spacing: 0.02em;
}

@media (max-width: 960px) {
  .inspector-shell {
    max-height: none;
    overflow: visible;
  }
  .summary-grid,
  .stack-grid {
    grid-template-columns: 1fr;
  }
}
</style>
