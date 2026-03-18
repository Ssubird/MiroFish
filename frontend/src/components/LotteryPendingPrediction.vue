<template>
  <section class="panel">
    <div class="panel-header">
      <div>
        <p class="eyebrow">PENDING</p>
        <h2>当前目标期方案</h2>
      </div>
      <span v-if="pendingPrediction" class="period-pill">{{ pendingPrediction.period }}</span>
    </div>

    <div v-if="!pendingPrediction" class="empty-state">当前没有待预测期，暂无可展示的市场方案。</div>

    <template v-else>
      <LotteryReportArtifacts :report-artifacts="reportArtifacts" />

      <article class="hero-card">
        <div class="result-block">
          <span class="label">参考票</span>
          <div class="ensemble-row">
            <span
              v-for="num in referenceNumbers"
              :key="`reference-${num}`"
              class="number-chip"
            >
              {{ num }}
            </span>
          </div>
        </div>

        <div class="result-block">
          <span class="label">对冲号 / 补位号</span>
          <div class="ensemble-row">
            <span
              v-for="num in hedgeNumbers"
              :key="`hedge-${num}`"
              class="number-chip alt"
            >
              {{ num }}
            </span>
          </div>
        </div>

        <div class="meta-list">
          <span v-if="pendingPrediction.purchase_plan?.plan_type" class="meta-tag">
            {{ pendingPrediction.purchase_plan.plan_type }}
          </span>
          <span v-if="pendingPrediction.purchase_plan?.play_size" class="meta-tag">
            选{{ pendingPrediction.purchase_plan.play_size }}
          </span>
          <span v-if="pendingPrediction.purchase_plan?.ticket_count" class="meta-tag">
            {{ pendingPrediction.purchase_plan.ticket_count }} 注
          </span>
          <span v-if="pendingPrediction.market_synthesis?.total_market_volume_yuan" class="meta-tag">
            市场成交 {{ pendingPrediction.market_synthesis.total_market_volume_yuan }} 元
          </span>
        </div>

        <div class="breakdown-list">
          <div v-for="item in scorePreview" :key="item.number" class="breakdown-item">
            <strong>{{ item.number }}</strong>
            <span>{{ item.score }}</span>
            <p>市场共识分数</p>
          </div>
        </div>
      </article>

      <div class="insight-grid">
        <article v-if="pendingPrediction.market_synthesis" class="insight-card">
          <div class="card-top">
            <strong>市场综合</strong>
            <span class="meta-tag">v2</span>
          </div>
          <p class="rationale">{{ pendingPrediction.market_synthesis.rationale }}</p>
          <div class="meta-list">
            <span
              v-for="item in pendingPrediction.market_synthesis.trusted_strategy_ids || []"
              :key="`market-${item}`"
              class="meta-tag"
            >
              {{ item }}
            </span>
          </div>
        </article>

        <article v-if="pendingPrediction.signal_outputs?.length" class="insight-card">
          <div class="card-top">
            <strong>信号开盘</strong>
            <span class="meta-tag">{{ pendingPrediction.signal_outputs.length }} 条</span>
          </div>
          <div class="stack-list">
            <div
              v-for="item in pendingPrediction.signal_outputs.slice(0, 4)"
              :key="item.strategy_id"
              class="stack-item"
            >
              <strong>{{ item.strategy_id }}</strong>
              <p>{{ item.public_post || '已生成结构化 signal output' }}</p>
            </div>
          </div>
        </article>

        <article v-if="bettorPlans.length" class="insight-card">
          <div class="card-top">
            <strong>投注人格</strong>
            <span class="meta-tag">{{ bettorPlans.length }} 份</span>
          </div>
          <div class="stack-list">
            <div
              v-for="item in bettorPlans.slice(0, 4)"
              :key="item.role_id"
              class="stack-item"
            >
              <strong>{{ item.display_name }}</strong>
              <p>{{ item.plan_type }} / 选{{ item.play_size }} / {{ item.risk_exposure }}</p>
            </div>
          </div>
        </article>

        <article v-if="pendingPrediction.live_interviews?.length" class="insight-card">
          <div class="card-top">
            <strong>系统访谈</strong>
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
        </article>
      </div>

      <LotteryPurchasePlan :purchase-plan="pendingPrediction.purchase_plan" />
    </template>
  </section>
</template>

<script setup>
import { computed } from 'vue'

import LotteryPurchasePlan from './LotteryPurchasePlan.vue'
import LotteryReportArtifacts from './LotteryReportArtifacts.vue'
import { groupLabel, kindLabel, shortText } from '../utils/lotteryDisplay'

const props = defineProps({
  pendingPrediction: {
    type: Object,
    default: null
  },
  reportArtifacts: {
    type: Object,
    default: null
  }
})

const marketSynthesis = computed(() => props.pendingPrediction?.market_synthesis || {})
const referenceNumbers = computed(() => {
  const numbers = marketSynthesis.value?.reference_leg?.numbers
  if (Array.isArray(numbers) && numbers.length) return numbers
  return props.pendingPrediction?.ensemble_numbers || []
})
const hedgeNumbers = computed(() => {
  const numbers = marketSynthesis.value?.hedge_pool
  if (Array.isArray(numbers) && numbers.length) return numbers
  return props.pendingPrediction?.alternate_numbers || []
})
const scorePreview = computed(() => (marketSynthesis.value?.consensus_number_scores || []).slice(0, 8))
const bettorPlans = computed(() => Object.values(props.pendingPrediction?.bet_plans || {}))
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
