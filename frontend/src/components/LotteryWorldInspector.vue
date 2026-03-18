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
      <article class="summary-card">
        <span>状态</span>
        <strong>{{ session?.status || '-' }}</strong>
      </article>
      <article class="summary-card">
        <span>阶段</span>
        <strong>{{ phaseLabel(session?.current_phase) }}</strong>
      </article>
      <article class="summary-card">
        <span>截止期</span>
        <strong>{{ session?.visible_through_period || latestPrediction?.visible_through_period || '-' }}</strong>
      </article>
      <article class="summary-card">
        <span>预测期</span>
        <strong>{{ latestPrediction?.predicted_period || latestPrediction?.period || '-' }}</strong>
      </article>
    </div>

    <article class="section-card status-card">
      <div class="section-head">
        <h3>进度</h3>
        <span>{{ activeModelName || '-' }}</span>
      </div>
      <div class="chip-row">
        <span class="chip">{{ phaseLabel(session?.current_phase) }}</span>
        <span class="chip">{{ progress.current_actor_name || '等待执行' }}</span>
        <span class="chip">
          讨论 {{ progress.dialogue_round_index || 0 }}/{{ progress.dialogue_round_total || 0 }}
        </span>
      </div>
      <p class="status-banner">{{ progress.completion_message || '等待下一步操作' }}</p>
    </article>

    <article class="section-card focus-card" :class="{ 'is-active': finalDecision }">
      <div class="section-head">
        <h3>官方最终结论</h3>
        <span>{{ finalDecision?.period || latestPrediction?.predicted_period || '-' }}</span>
      </div>
      <div class="chip-row">
        <span v-for="num in finalDecision?.numbers || latestPrediction?.ensemble_numbers || []" :key="`f-${num}`" class="chip primary">{{ num }}</span>
        <span v-for="num in finalDecision?.alternate_numbers || latestPrediction?.alternate_numbers || []" :key="`fa-${num}`" class="chip alt">{{ num }}</span>
      </div>
      <p>{{ shortText(finalDecision?.rationale, 240) || '本轮还没有形成官方终判。' }}</p>
      <p class="muted">{{ shortText(finalDecision?.risk_note, 180) }}</p>
    </article>

    <div class="stack-grid">
      <article class="section-card compact">
        <div class="section-head">
          <h3>购买建议</h3>
          <span>{{ latestPurchasePlan?.plan_type || latestPurchasePlan?.status || '-' }}</span>
        </div>
        <div class="chip-row">
          <span class="chip">{{ latestPurchasePlan?.play_size ? `选${latestPurchasePlan.play_size}` : '-' }}</span>
          <span class="chip">{{ latestPurchasePlan?.ticket_count || 0 }} 注</span>
          <span class="chip">{{ latestPurchasePlan?.total_cost_yuan || budgetYuan || 0 }} 元</span>
        </div>
        <p>{{ shortText(latestPurchasePlan?.rationale || latestPurchasePlan?.chosen_edge, 180) || '购买建议尚未生成。' }}</p>
      </article>

      <article class="section-card compact">
        <div class="section-head">
          <h3>最新复盘</h3>
          <span>{{ latestReview?.period || '-' }}</span>
        </div>
        <div class="chip-row">
          <span class="chip">官方命中 {{ latestReview?.official_hits ?? '-' }}</span>
          <span class="chip">收益 {{ latestReview?.purchase_profit ?? '-' }}</span>
          <span class="chip">ROI {{ latestReview?.purchase_roi ?? '-' }}</span>
        </div>
        <p>{{ shortText(latestReview?.summary, 180) || '当前还没有复盘结果。' }}</p>
      </article>
    </div>

    <article class="section-card">
      <div class="section-head">
        <h3>生成组结论</h3>
        <span>{{ generatorBoards.length }}</span>
      </div>
      <div v-if="!generatorBoards.length" class="empty-log">当前还没有生成组结果。</div>
      <div v-else class="event-list">
        <div v-for="item in generatorBoards" :key="item.strategy_id" class="event-item">
          <strong>{{ item.strategy_id }}</strong>
          <span>{{ groupLabel(item.regime_label || item.group || '-') }}</span>
          <p>Top: {{ topNumbers(item) }}</p>
        </div>
      </div>
    </article>

    <article class="section-card">
      <div class="section-head">
        <h3>市场讨论</h3>
        <span>{{ marketPosts.length + judgeBoards.length }}</span>
      </div>
      <div v-if="!marketPosts.length && !judgeBoards.length" class="empty-log">当前还没有市场讨论记录。</div>
      <div v-else class="event-list">
        <div v-for="item in marketPosts" :key="item.event_id || `social-${item.actor_id}`" class="event-item">
          <strong>{{ item.actor_display_name || item.actor_id }}</strong>
          <span>市场发言</span>
          <p>{{ shortText(item.content, 160) }}</p>
        </div>
        <div v-for="item in judgeBoards" :key="item.event_id || `judge-${item.actor_id}`" class="event-item">
          <strong>{{ item.actor_display_name || item.actor_id }}</strong>
          <span>裁判意见</span>
          <p>{{ shortText(item.content, 160) }}</p>
        </div>
      </div>
    </article>

    <article class="section-card">
      <div class="section-head">
        <h3>命中总账</h3>
        <span>{{ issueLedger.length }}</span>
      </div>
      <div v-if="!issueLedger.length" class="empty-log">当前还没有已结算期数。</div>
      <div v-else class="event-list">
        <div v-for="item in issueLedger.slice().reverse()" :key="item.predicted_period" class="event-item">
          <strong>{{ item.predicted_period }} 期</strong>
          <span>命中 {{ item.official_hits }} / 收益 {{ item.purchase_recommendation?.profit_yuan ?? '-' }}</span>
          <p>
            官方 {{ listLine(item.official_prediction) }} / 实际 {{ listLine(item.actual_numbers) }}
          </p>
        </div>
      </div>
    </article>

    <article class="section-card">
      <div class="section-head">
        <h3>文件与报告</h3>
        <span>{{ reportArtifacts?.run_id || '-' }}</span>
      </div>
      <div class="event-list">
        <div class="event-item">
          <strong>运行报告</strong>
          <span>{{ reportArtifacts?.markdown_path || '-' }}</span>
          <p>{{ reportArtifacts?.json_path || '-' }}</p>
        </div>
        <div v-if="reportArtifacts?.issue_ledger" class="event-item">
          <strong>命中总账</strong>
          <span>{{ reportArtifacts.issue_ledger.markdown_path }}</span>
          <p>{{ reportArtifacts.issue_ledger.json_path }}</p>
        </div>
        <div
          v-for="item in reportArtifacts?.issue_reports || []"
          :key="item.predicted_period"
          class="event-item"
        >
          <strong>{{ item.predicted_period }} 期报告</strong>
          <span>{{ item.markdown_path }}</span>
          <p>{{ item.json_path }}</p>
        </div>
      </div>
    </article>

    <article class="section-card focus-card" :class="{ 'is-active': selectedGraphNode }">
      <div class="section-head">
        <h3>选中节点</h3>
        <span>{{ selectedGraphNode?.label || '-' }}</span>
      </div>
      <p v-if="!selectedGraphNode" class="muted">点击中间图谱节点后，这里会显示辅助详情。</p>
      <template v-else>
        <div class="chip-row">
          <span class="chip">{{ nodeTypeLabel(selectedGraphNode.node_type) }}</span>
          <span class="chip">{{ nodeScope(selectedGraphNode) }}</span>
        </div>
        <p>{{ selectedGraphNode.summary || selectedGraphNode.comment || '-' }}</p>
      </template>
    </article>

    <article class="section-card focus-card" :class="{ 'is-active': selectedNumberDetail }">
      <div class="section-head">
        <h3>选中号码</h3>
        <span>{{ selectedNumberDetail?.number || '-' }}</span>
      </div>
      <p v-if="!selectedNumberDetail" class="muted">点击底部号码板后，这里会显示最近轨迹。</p>
      <template v-else>
        <div class="chip-row">
          <span class="chip">出现 {{ selectedNumberDetail.count }} 次</span>
          <span class="chip">提及 {{ selectedNumberDetail.mention_count }} 次</span>
        </div>
        <p>最近期次：{{ (selectedNumberDetail.periods || []).join(' / ') || '-' }}</p>
      </template>
    </article>

    <article class="section-card">
      <div class="section-head">
        <h3>深度互动</h3>
        <span>{{ liveInterviewEnabled ? '会写入时间线' : '当前已关闭' }}</span>
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
            placeholder="例如：你为什么保留这组号码？"
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
        <h3>执行日志</h3>
        <span>{{ executionLogs.length }}</span>
      </div>
      <div v-if="!executionLogs.length" class="empty-log">当前还没有执行日志。</div>
      <div v-else class="log-list">
        <div v-for="entry in executionLogs" :key="entry.log_id || `${entry.created_at}-${entry.code}`" class="log-item">
          <div class="log-head">
            <strong :class="`level-${entry.level || 'info'}`">{{ logLevelLabel(entry.level) }}</strong>
            <span>{{ phaseLabel(entry.phase) }} / {{ formatLogTime(entry.created_at) }}</span>
          </div>
          <div class="log-code">{{ entry.code || '-' }}</div>
          <p>{{ entry.message || '-' }}</p>
        </div>
      </div>
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

import {
  eventLabel,
  groupLabel,
  logLevelLabel,
  nodeTypeLabel,
  phaseLabel,
  shortText
} from '../utils/lotteryDisplay'

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
const executionLogs = computed(() => [...(session.value?.execution_log || [])].reverse().slice(0, 16))
const progress = computed(() => session.value?.progress || {})
const finalDecision = computed(() => props.latestPrediction?.final_decision || null)
const latestReview = computed(() => props.latestPrediction?.latest_review || session.value?.latest_review || null)
const generatorBoards = computed(() => props.latestPrediction?.generator_boards || [])
const marketDiscussion = computed(() => props.latestPrediction?.market_discussion || {})
const marketPosts = computed(() => marketDiscussion.value.social_posts || [])
const judgeBoards = computed(() => marketDiscussion.value.judge_boards || [])
const issueLedger = computed(() => session.value?.issue_ledger || [])
const reportArtifacts = computed(() => session.value?.report_artifacts || props.sessionData?.report_artifacts || null)

const nodeScope = (node) => {
  if (!node) return '-'
  if (node.node_type === 'phase' || node.node_type === 'debate_round') return phaseLabel(node.phase)
  return groupLabel(node.group || '-')
}

const formatLogTime = (value) => {
  const text = String(value || '').trim()
  if (!text) return '-'
  return text.replace('T', ' ').replace('Z', '')
}

const listLine = (values) => (values || []).join(' / ') || '-'

const topNumbers = (item) => {
  const rows = Object.entries(item.number_scores || {})
    .map(([number, score]) => ({ number, score: Number(score) }))
    .sort((left, right) => right.score - left.score || Number(left.number) - Number(right.number))
    .slice(0, 6)
  return rows.map((row) => row.number).join(' / ') || '-'
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
  color: #e0e6ed;
}

.summary-grid,
.stack-grid,
.event-list,
.form-grid,
.log-list {
  display: grid;
  gap: 1rem;
}

.summary-grid,
.stack-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.inspector-header,
.header-actions,
.section-head,
.chip-row,
.log-head {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.inspector-header,
.section-head,
.log-head {
  justify-content: space-between;
}

.summary-card,
.section-card,
.event-item,
.log-item {
  display: grid;
  gap: 0.75rem;
  padding: 1rem;
  border-radius: 1rem;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.03);
}

.focus-card {
  border-color: rgba(0, 240, 255, 0.2);
}

.focus-card.is-active,
.status-card {
  background: rgba(0, 240, 255, 0.08);
}

.status-banner {
  margin: 0;
  padding: 0.75rem 1rem;
  border-radius: 0.85rem;
  background: rgba(255, 255, 255, 0.05);
  color: #fff;
}

.summary-card strong,
.summary-card span,
.section-card p,
.event-item p,
.event-item span,
.section-head span,
.eyebrow,
.section-head h3,
.inspector-header h2,
.empty-log {
  margin: 0;
}

.summary-card strong {
  display: block;
  font-size: 1.15rem;
  color: #fff;
}

.section-head h3 {
  font-size: 1.1rem;
  font-weight: 600;
  color: #fff;
}

.section-head span,
.eyebrow,
.muted,
.empty-log,
.event-item span,
.log-code {
  color: #8b9bb4;
}

.chip {
  display: inline-flex;
  align-items: center;
  padding: 0.25rem 0.75rem;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.15);
  background: rgba(255, 255, 255, 0.05);
  font-size: 0.85rem;
}

.chip.primary {
  background: rgba(0, 240, 255, 0.15);
  border-color: rgba(0, 240, 255, 0.4);
  color: #00f0ff;
}

.chip.alt {
  background: rgba(255, 193, 77, 0.12);
  border-color: rgba(255, 193, 77, 0.4);
  color: #ffc14d;
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
  font-weight: 600;
}

.ghost-btn {
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(255, 255, 255, 0.05);
  color: #a0b2c6;
}

.ghost-btn.danger {
  color: #ff8c8c;
  border-color: rgba(255, 140, 140, 0.35);
}

.run-btn {
  border: 1px solid rgba(0, 240, 255, 0.4);
  background: rgba(0, 240, 255, 0.1);
  color: #00f0ff;
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
}

.event-list,
.log-list {
  max-height: 18rem;
  overflow: auto;
  padding-right: 0.5rem;
}

.event-item strong {
  color: #00f0ff;
}

.log-item p {
  margin: 0;
}

.level-info {
  color: #7ce8ff;
}

.level-warning {
  color: #ffd66b;
}

.level-error {
  color: #ff8c8c;
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
