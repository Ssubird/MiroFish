<template>
  <section class="panel">
    <div class="panel-header">
      <div>
        <p class="eyebrow">PENDING</p>
        <h2>当前目标期结论</h2>
      </div>
      <span v-if="pendingPrediction" class="period-pill">{{ pendingPrediction.period }}</span>
    </div>

    <div v-if="!pendingPrediction" class="empty-state">当前没有待预测期，无法展示结论。</div>

    <template v-else>
      <LotteryReportArtifacts :report-artifacts="reportArtifacts" />

      <article class="hero-card">
        <div class="result-block">
          <span class="label">Primary 5</span>
          <div class="ensemble-row">
            <span v-for="num in pendingPrediction.ensemble_numbers" :key="`ensemble-${num}`" class="number-chip">
              {{ num }}
            </span>
          </div>
        </div>

        <div class="result-block">
          <span class="label">Alternate 3</span>
          <div class="ensemble-row">
            <span v-for="num in pendingPrediction.alternate_numbers || []" :key="`alternate-${num}`" class="number-chip alt">
              {{ num }}
            </span>
          </div>
        </div>

        <div class="meta-list">
          <span v-if="pendingPrediction.purchase_plan?.plan_type" class="meta-tag">
            purchase {{ pendingPrediction.purchase_plan.plan_type }}
          </span>
          <span v-if="pendingPrediction.purchase_plan?.play_size" class="meta-tag">
            选{{ pendingPrediction.purchase_plan.play_size }}
          </span>
          <span v-if="pendingPrediction.purchase_plan?.ticket_count" class="meta-tag">
            {{ pendingPrediction.purchase_plan.ticket_count }} 注
          </span>
        </div>

        <div v-if="pendingPrediction.contributors?.length" class="meta-section">
          <span>融合贡献者</span>
          <div class="meta-list">
            <span v-for="item in pendingPrediction.contributors" :key="item.strategy_id" class="meta-tag">
              {{ groupLabel(item.group) }} / {{ item.display_name }}
            </span>
          </div>
        </div>

        <div class="breakdown-list">
          <div v-for="item in pendingPrediction.ensemble_breakdown" :key="item.number" class="breakdown-item">
            <strong>{{ item.number }}</strong>
            <span>{{ item.score }}</span>
            <p>{{ item.sources.join(' / ') }}</p>
          </div>
        </div>
      </article>

      <div class="insight-grid">
        <article v-if="pendingPrediction.judge_decision" class="insight-card">
          <div class="card-top">
            <strong>裁判定稿</strong>
            <span class="meta-tag">judge</span>
          </div>
          <p class="rationale">{{ pendingPrediction.judge_decision.rationale }}</p>
          <div class="meta-list">
            <span
              v-for="item in pendingPrediction.judge_decision.trusted_strategy_ids || []"
              :key="`judge-${item}`"
              class="meta-tag"
            >
              {{ item }}
            </span>
          </div>
        </article>

        <article v-if="pendingPrediction.live_interviews?.length" class="insight-card">
          <div class="card-top">
            <strong>系统采访</strong>
            <span class="meta-tag">{{ pendingPrediction.live_interviews.length }} 条</span>
          </div>
          <div class="stack-list">
            <div
              v-for="item in pendingPrediction.live_interviews.slice(0, 3)"
              :key="item.agent_id + item.created_at"
              class="stack-item"
            >
              <strong>{{ item.agent_id }}</strong>
              <p>{{ shortText(item.answer, 140) }}</p>
            </div>
          </div>
        </article>

        <article v-if="pendingPrediction.world_timeline_preview?.length" class="insight-card">
          <div class="card-top">
            <strong>世界预览</strong>
            <span class="meta-tag">{{ pendingPrediction.world_timeline_preview.length }} 条</span>
          </div>
          <div class="stack-list">
            <div
              v-for="item in pendingPrediction.world_timeline_preview.slice(0, 4)"
              :key="item.event_id || item.actor_id + item.created_at"
              class="stack-item"
            >
              <strong>{{ item.actor_display_name || item.actor_id }}</strong>
              <p>{{ shortText(item.content || item.comment, 140) }}</p>
            </div>
          </div>
        </article>
      </div>

      <div class="strategy-grid">
        <article v-for="item in pendingPrediction.strategy_predictions" :key="item.strategy_id" class="strategy-card">
          <div class="card-top">
            <div>
              <strong>{{ item.display_name }}</strong>
              <p>{{ item.strategy_id }}</p>
            </div>
            <span class="avg-badge">avg {{ item.backtest_average_hits }}</span>
          </div>

          <div class="tag-row">
            <span class="meta-tag">{{ groupLabel(item.group) }}</span>
            <span class="kind-tag" :class="item.kind">{{ kindLabel(item.kind) }}</span>
            <span v-if="item.metadata?.model" class="meta-tag">{{ item.metadata.model }}</span>
          </div>

          <div class="number-row">
            <span v-for="num in item.numbers" :key="`${item.strategy_id}-${num}`" class="number-chip alt">{{ num }}</span>
          </div>

          <p class="rationale">{{ item.rationale }}</p>

          <div v-if="sourceList(item).length" class="meta-section">
            <span>知识来源</span>
            <div class="meta-list">
              <span v-for="source in sourceList(item)" :key="`${item.strategy_id}-${source}`" class="meta-tag">
                {{ source }}
              </span>
            </div>
          </div>

          <div v-if="focusList(item).length" class="meta-section">
            <span>关注点</span>
            <div class="meta-list">
              <span v-for="focus in focusList(item)" :key="`${item.strategy_id}-${focus}`" class="meta-tag">
                {{ focus }}
              </span>
            </div>
          </div>
        </article>
      </div>

      <LotteryPurchasePlan :purchase-plan="pendingPrediction.purchase_plan" />
    </template>
  </section>
</template>

<script setup>
import LotteryPurchasePlan from './LotteryPurchasePlan.vue'
import LotteryReportArtifacts from './LotteryReportArtifacts.vue'
import { groupLabel, kindLabel, shortText } from '../utils/lotteryDisplay'

defineProps({
  pendingPrediction: {
    type: Object,
    default: null
  },
  reportArtifacts: {
    type: Object,
    default: null
  }
})

const sourceList = (item) => (Array.isArray(item.metadata?.sources) ? item.metadata.sources : [])
const focusList = (item) => (Array.isArray(item.metadata?.focus) ? item.metadata.focus : [])
</script>

<style scoped>
.panel,
.hero-card,
.strategy-card,
.insight-card {
  display: grid;
  gap: 1rem;
}

.panel {
  padding: 1.35rem;
  border-radius: 1.5rem;
  background: var(--lottery-panel, rgba(255, 251, 244, 0.92));
  border: 1px solid var(--lottery-line, rgba(31, 28, 24, 0.1));
  box-shadow: var(--lottery-shadow, 0 18px 40px rgba(24, 22, 19, 0.08));
}

.panel-header,
.card-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 0.8rem;
}

.eyebrow,
.label,
.strategy-card p,
.meta-section span,
.breakdown-item p,
.rationale,
.stack-item p {
  margin: 0;
  font-size: 0.82rem;
  line-height: 1.6;
  color: var(--lottery-muted, #6e675f);
}

.period-pill,
.avg-badge,
.meta-tag,
.kind-tag {
  display: inline-flex;
  align-items: center;
  padding: 0.32rem 0.7rem;
  border-radius: 999px;
  font-size: 0.76rem;
}

.period-pill,
.meta-tag {
  background: rgba(255, 255, 255, 0.75);
  border: 1px solid var(--lottery-line-strong, rgba(31, 28, 24, 0.16));
}

.avg-badge,
.kind-tag.llm {
  background: var(--lottery-ink, #1d1b19);
  color: #fff;
}

.empty-state {
  padding: 1.2rem;
  border-radius: 1.2rem;
  border: 1px dashed var(--lottery-line-strong, rgba(31, 28, 24, 0.16));
  color: var(--lottery-muted, #6e675f);
}

.hero-card,
.strategy-card,
.insight-card {
  padding: 1rem;
  border-radius: 1.15rem;
  border: 1px solid var(--lottery-line, rgba(31, 28, 24, 0.1));
  background: rgba(255, 255, 255, 0.72);
}

.ensemble-row,
.number-row,
.tag-row,
.meta-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.55rem;
}

.number-chip {
  display: inline-flex;
  justify-content: center;
  align-items: center;
  min-width: 2.7rem;
  padding: 0.6rem 0.8rem;
  border-radius: 999px;
  background: var(--lottery-ink, #1d1b19);
  color: #fff;
}

.number-chip.alt {
  background: rgba(255, 255, 255, 0.82);
  color: var(--lottery-ink, #1d1b19);
  border: 1px solid var(--lottery-line-strong, rgba(31, 28, 24, 0.16));
}

.breakdown-list,
.insight-grid,
.strategy-grid {
  display: grid;
  gap: 0.75rem;
}

.breakdown-list,
.insight-grid {
  grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));
}

.strategy-grid {
  grid-template-columns: repeat(auto-fit, minmax(18rem, 1fr));
}

.breakdown-item,
.stack-item {
  display: grid;
  gap: 0.3rem;
  padding: 0.9rem;
  border-radius: 1rem;
  background: rgba(246, 243, 236, 0.8);
}

.meta-section,
.stack-list,
.result-block {
  display: grid;
  gap: 0.55rem;
}
</style>
