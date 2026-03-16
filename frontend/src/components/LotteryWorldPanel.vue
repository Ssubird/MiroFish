<template>
  <section class="panel">
    <div class="panel-header">
      <div>
        <p class="eyebrow">WORLD</p>
        <h2>持续预测世界</h2>
      </div>
      <div class="header-actions">
        <button class="ghost-btn" :disabled="loading || !session" @click="$emit('refresh')">刷新</button>
        <button class="ghost-btn" :disabled="loading" @click="$emit('reset')">清空状态</button>
        <span v-if="session?.session_id" class="session-pill">{{ session.session_id }}</span>
      </div>
    </div>

    <div v-if="!session" class="empty-state">
      首次运行后，这里会显示当前目标期、阶段推进、中间结论、购买委员会和世界时间线。
    </div>

    <template v-else>
      <div class="summary-grid">
        <article class="summary-card"><span>状态</span><strong>{{ session.status || '-' }}</strong></article>
        <article class="summary-card"><span>当前阶段</span><strong>{{ phaseLabel(session.current_phase) }}</strong></article>
        <article class="summary-card"><span>当前期号</span><strong>{{ session.current_period || '-' }}</strong></article>
        <article class="summary-card"><span>预算</span><strong>{{ session.budget_yuan || budgetYuan || 50 }} 元</strong></article>
        <article class="summary-card"><span>已结算轮次</span><strong>{{ progress.settled_rounds || 0 }}</strong></article>
        <article class="summary-card"><span>LLM 请求</span><strong>{{ requestMetrics.send_message || 0 }}</strong></article>
      </div>

      <article class="section-card">
        <div class="section-head">
          <h3>阶段流</h3>
          <span>{{ session.llm_model_name || '默认模型' }}</span>
        </div>
        <div class="phase-grid">
          <div v-for="item in phaseCards" :key="item.id" class="phase-card" :class="item.state">
            <strong>{{ item.label }}</strong>
            <p>{{ item.note }}</p>
          </div>
        </div>
      </article>

      <div class="dual-grid">
        <article class="section-card">
          <div class="section-head">
            <h3>中间结论</h3>
            <span>{{ latestSummary.period || '-' }}</span>
          </div>
          <div class="number-strip">
            <span v-for="num in latestSummary.primary_numbers || []" :key="`p-${num}`" class="number-chip">{{ num }}</span>
            <span v-for="num in latestSummary.alternate_numbers || []" :key="`a-${num}`" class="number-chip alt">{{ num }}</span>
          </div>
          <div class="chip-row">
            <span v-for="item in latestSummary.trusted_strategy_ids || []" :key="item" class="chip">{{ item }}</span>
          </div>
          <p class="muted">
            phase={{ latestSummary.phase || '-' }} / plan={{ latestSummary.purchase_plan_type || '-' }} /
            play={{ latestSummary.purchase_play_size || '-' }} / tickets={{ latestSummary.purchase_ticket_count || 0 }}
          </p>
        </article>

        <article class="section-card">
          <div class="section-head">
            <h3>当前轮状态</h3>
            <span>{{ currentRound.target_period || '-' }}</span>
          </div>
          <p class="muted">status={{ currentRound.status || '-' }} / updated={{ currentRound.updated_at || '-' }}</p>
          <div class="chip-row">
            <span v-for="item in session.active_agent_ids || []" :key="item" class="chip active">{{ item }}</span>
          </div>
          <p>{{ shortText(sharedMemory.current_issue, 260) || '当前暂无问题摘要。' }}</p>
        </article>
      </div>

      <article v-if="session.error?.message" class="error-state">
        <strong>运行失败</strong>
        <p>{{ session.error.message }}</p>
        <span>阶段：{{ phaseLabel(session.error.phase) }} / 期号：{{ session.error.period || '-' }}</span>
      </article>

      <div class="memory-grid">
        <article v-for="item in memoryEntries" :key="item.key" class="memory-card">
          <div class="section-head">
            <h3>{{ item.label }}</h3>
          </div>
          <p>{{ shortText(item.value, 220) || '当前为空' }}</p>
        </article>
      </div>

      <div class="dual-grid">
        <article class="section-card">
          <div class="section-head">
            <h3>资产清单</h3>
            <span>{{ assetManifest.length }} items</span>
          </div>
          <div v-if="!assetManifest.length" class="empty-state">暂无资产清单。</div>
          <div v-else class="asset-list">
            <article v-for="item in assetManifest" :key="item.path" class="asset-card">
              <div class="agent-top">
                <div>
                  <strong>{{ item.name }}</strong>
                  <p>{{ item.role }}</p>
                </div>
                <span class="event-pill" :class="{ inactive: !item.active }">{{ item.active ? 'active' : 'manual' }}</span>
              </div>
              <p class="muted">{{ item.path }}</p>
              <p>{{ item.note }}</p>
            </article>
          </div>
        </article>

        <article class="section-card">
          <div class="section-head">
            <h3>人工参考</h3>
            <span>{{ manualReferences.length }}</span>
          </div>
          <div v-if="!manualReferences.length" class="empty-state">当前没有人工参考文件。</div>
          <div v-else class="asset-list">
            <article v-for="item in manualReferences" :key="item.path" class="asset-card">
              <strong>{{ item.name }}</strong>
              <p class="muted">{{ item.path }}</p>
              <p>仅供人工查看，不会进入 agent 输入。</p>
            </article>
          </div>
        </article>
      </div>

      <article class="section-card">
        <div class="section-head">
          <h3>购买委员会</h3>
          <span>{{ committee.plan_type || committee.status || '-' }}</span>
        </div>
        <div class="chip-row">
          <span class="chip active">预算 {{ committee.budget_yuan || budgetYuan || 50 }} 元</span>
          <span class="chip">玩法 选{{ committee.play_size || '-' }}</span>
          <span class="chip">票数 {{ committee.ticket_count || 0 }}</span>
          <span class="chip">成本 {{ committee.total_cost_yuan || 0 }} 元</span>
        </div>
        <p>{{ shortText(committee.planner?.rationale || committee.rationale, 220) || '当前还在讨论中。' }}</p>
      </article>

      <article class="section-card">
        <div class="section-head">
          <h3>真人追问</h3>
          <span>{{ liveInterviewEnabled ? '会写入世界时间线' : '当前关闭' }}</span>
        </div>
        <div class="form-grid">
          <label class="field">
            <span>Agent</span>
            <select :value="agentId" @change="$emit('update:agentId', $event.target.value)">
              <option value="">请选择</option>
              <option v-for="agent in agentOptions" :key="agent.session_agent_id" :value="agent.session_agent_id">
                {{ agent.display_name }} / {{ agent.session_agent_id }}
              </option>
            </select>
          </label>
          <label class="field wide">
            <span>Prompt</span>
            <textarea
              :value="prompt"
              rows="3"
              placeholder="例如：你为什么还坚持这组号码？"
              @input="$emit('update:prompt', $event.target.value)"
            />
          </label>
        </div>
        <button class="run-btn" :disabled="interviewBusy || !liveInterviewEnabled || !agentId || !prompt.trim()" @click="$emit('interview')">
          {{ interviewBusy ? '发送中...' : '发送追问' }}
        </button>
      </article>

      <article class="section-card">
        <div class="section-head">
          <h3>最新世界事件</h3>
          <span>{{ timeline?.total || 0 }} 条事件</span>
        </div>
        <div v-if="!latestEvents.length" class="empty-state">当前还没有可展示的世界事件。</div>
        <div v-else class="timeline-list">
          <article v-for="event in latestEvents" :key="event.event_id" class="timeline-item">
            <div class="agent-top">
              <div>
                <strong>{{ event.actor_display_name }}</strong>
                <p>{{ event.actor_id }} / {{ phaseLabel(event.phase) }}</p>
              </div>
              <span class="event-pill">{{ eventLabel(event.event_type) }}</span>
            </div>
            <div v-if="event.numbers?.length" class="chip-row">
              <span v-for="num in event.numbers" :key="`${event.event_id}-${num}`" class="chip active">{{ num }}</span>
            </div>
            <p>{{ shortText(event.content, 300) }}</p>
          </article>
        </div>
      </article>
    </template>
  </section>
</template>

<script setup>
import { computed } from 'vue'

import { eventLabel, phaseLabel, shortText } from '../utils/lotteryDisplay'

const props = defineProps({
  sessionData: { type: Object, default: null },
  timeline: { type: Object, default: () => ({ items: [], total: 0 }) },
  loading: { type: Boolean, default: false },
  budgetYuan: { type: Number, default: 50 },
  interviewBusy: { type: Boolean, default: false },
  liveInterviewEnabled: { type: Boolean, default: true },
  agentId: { type: String, default: '' },
  prompt: { type: String, default: '' }
})

defineEmits(['refresh', 'reset', 'interview', 'update:agentId', 'update:prompt'])

const session = computed(() => props.sessionData?.session || null)
const progress = computed(() => session.value?.progress || {})
const latestSummary = computed(() => session.value?.latest_issue_summary || {})
const committee = computed(() => props.sessionData?.purchase_committee_state || {})
const requestMetrics = computed(() => session.value?.request_metrics || {})
const latestEvents = computed(() => props.timeline?.items || [])
const agentOptions = computed(() => session.value?.agents || [])
const currentRound = computed(() => session.value?.current_round || {})
const sharedMemory = computed(() => session.value?.shared_memory || {})
const assetManifest = computed(() => session.value?.asset_manifest || [])
const manualReferences = computed(() => session.value?.manual_reference_documents || [])

const memoryEntries = computed(() => {
  const labels = {
    world_goal: '世界目标',
    current_issue: '当前问题',
    recent_outcomes: '近期结果',
    report_digest: '文件使用策略',
    rule_digest: '规则摘要',
    purchase_budget: '购买预算'
  }
  return Object.entries(labels).map(([key, label]) => ({ key, label, value: sharedMemory.value[key] || '' }))
})

const phaseCards = computed(() => {
  const order = ['opening', 'rule_interpretation', 'public_debate', 'judge_synthesis', 'purchase_committee', 'await_result', 'settlement', 'postmortem']
  const notes = {
    opening: '主策略和公共节点先发出开场候选。',
    rule_interpretation: '规则结果转成人话再入场。',
    public_debate: '各角色公开讨论、引用彼此并修正号码。',
    judge_synthesis: '裁判收束为 5 主号 + 3 备号。',
    purchase_committee: '在预算下讨论玩法、结构和票面。',
    await_result: '等待真实开奖进入数据文件。',
    settlement: '写入真实结果与收益结算。',
    postmortem: '复盘修正并保留状态。'
  }
  const current = session.value?.current_phase || 'idle'
  const activeIndex = order.indexOf(current)
  return order.map((id, index) => ({
    id,
    label: phaseLabel(id),
    note: notes[id],
    state: current === 'failed' ? 'idle' : index < activeIndex ? 'done' : index === activeIndex ? 'active' : 'idle'
  }))
})
</script>

<style scoped>
.panel,
.summary-grid,
.phase-grid,
.dual-grid,
.memory-grid,
.timeline-list,
.asset-list {
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

.panel-header,
.header-actions,
.section-head,
.agent-top,
.chip-row,
.form-grid,
.number-strip {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
  align-items: center;
}

.panel-header,
.section-head {
  justify-content: space-between;
}

.summary-grid,
.phase-grid,
.dual-grid,
.memory-grid {
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
}

.summary-card,
.section-card,
.memory-card,
.asset-card,
.timeline-item {
  border: 1px solid rgba(31, 28, 24, 0.08);
  border-radius: 1rem;
  padding: 1rem;
  background: rgba(255, 255, 255, 0.82);
}

.phase-card.active {
  border-color: rgba(171, 98, 43, 0.45);
  background: rgba(255, 242, 224, 0.95);
}

.phase-card.done {
  border-color: rgba(78, 125, 71, 0.32);
  background: rgba(236, 248, 235, 0.95);
}

.empty-state,
.error-state {
  padding: 1rem;
  border-radius: 1rem;
  border: 1px dashed rgba(31, 28, 24, 0.18);
  background: rgba(255, 255, 255, 0.62);
}

.error-state {
  border-style: solid;
  border-color: rgba(160, 55, 55, 0.28);
  background: rgba(255, 240, 240, 0.9);
}

.ghost-btn,
.run-btn {
  border: 1px solid var(--lottery-line-strong, rgba(31, 28, 24, 0.16));
  border-radius: 999px;
  padding: 0.55rem 0.95rem;
  background: rgba(255, 255, 255, 0.88);
  cursor: pointer;
  font: inherit;
}

.run-btn {
  background: var(--lottery-ink, #1d1b19);
  color: #fff;
}

.session-pill,
.event-pill,
.chip,
.number-chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 2rem;
  border-radius: 999px;
  padding: 0.28rem 0.7rem;
  border: 1px solid rgba(31, 28, 24, 0.14);
  background: rgba(255, 255, 255, 0.9);
}

.number-chip.alt,
.chip.active,
.event-pill {
  background: var(--lottery-ink, #1d1b19);
  color: #fff;
}

.event-pill.inactive {
  background: rgba(196, 140, 76, 0.14);
  color: #8b5a23;
}

.field {
  display: grid;
  gap: 0.45rem;
  flex: 1 1 14rem;
}

.field.wide {
  flex-basis: 100%;
}

select,
textarea {
  width: 100%;
  border-radius: 0.95rem;
  border: 1px solid rgba(31, 28, 24, 0.16);
  padding: 0.8rem 0.9rem;
  font: inherit;
  background: rgba(255, 255, 255, 0.88);
}

.eyebrow,
.muted,
.timeline-item p,
.asset-card p {
  margin: 0;
  color: var(--lottery-muted, #6e675f);
}
</style>
