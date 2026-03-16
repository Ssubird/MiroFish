<template>
  <article v-if="purchasePlan" class="panel">
    <div class="panel-header">
      <div>
        <p class="eyebrow">PURCHASE</p>
        <h3>购买方案</h3>
      </div>
      <span class="status-pill" :class="purchasePlan.status">{{ purchasePlan.status }}</span>
    </div>

    <div v-if="purchasePlan.status !== 'ready'" class="empty-state">
      {{ purchasePlan.reason }}
    </div>

    <template v-else>
      <div class="stats-grid">
        <div class="stat-card">
          <span>预算</span>
          <strong>{{ purchasePlan.budget_yuan }} 元</strong>
        </div>
        <div class="stat-card">
          <span>方案类型</span>
          <strong>{{ purchasePlan.plan_type || '-' }}</strong>
        </div>
        <div class="stat-card">
          <span>总票数</span>
          <strong>{{ purchasePlan.ticket_count }} 注</strong>
        </div>
        <div class="stat-card">
          <span>总成本</span>
          <strong>{{ purchasePlan.total_cost_yuan }} 元</strong>
        </div>
        <div class="stat-card">
          <span>单注成本</span>
          <strong>{{ purchasePlan.ticket_cost_yuan }} 元</strong>
        </div>
      </div>

      <div class="planner-card">
        <div class="card-top">
          <div>
            <strong>{{ purchasePlan.planner?.display_name }}</strong>
            <p>{{ purchasePlan.planner?.model }}</p>
          </div>
          <span class="pill">{{ purchasePlan.planner?.plan_style || purchasePlan.plan_type }}</span>
        </div>
        <p class="rationale">{{ purchasePlan.planner?.rationale }}</p>
        <p class="rationale" v-if="purchasePlan.chosen_edge">
          决策边：{{ purchasePlan.chosen_edge }}
        </p>
        <div class="tag-block">
          <span v-for="num in purchasePlan.planner?.primary_ticket || []" :key="`ticket-${num}`" class="tag primary">{{ num }}</span>
          <span v-for="num in purchasePlan.planner?.core_numbers || []" :key="`core-${num}`" class="tag core">{{ num }}</span>
          <span v-for="num in purchasePlan.planner?.hedge_numbers || []" :key="`hedge-${num}`" class="tag hedge">{{ num }}</span>
          <span v-for="num in purchasePlan.planner?.avoid_numbers || []" :key="`avoid-${num}`" class="tag avoid">{{ num }}</span>
        </div>
      </div>

      <div v-if="reviewRows.length" class="portfolio-card">
        <h4>玩法比较</h4>
        <div class="portfolio-grid">
          <div v-for="item in reviewRows" :key="item.key" class="portfolio-item">
            <strong>选{{ item.key }}</strong>
            <p>{{ item.value }}</p>
          </div>
        </div>
      </div>

      <div v-if="portfolioLegs.length" class="portfolio-card">
        <h4>组合方案</h4>
        <div class="portfolio-grid">
          <div v-for="leg in portfolioLegs" :key="leg.index" class="portfolio-item">
            <strong>腿 {{ leg.index }}</strong>
            <span>{{ leg.plan_type }} / {{ leg.play_label || `选${leg.play_size}` }}</span>
            <span>{{ leg.ticket_count || leg.combination_count || 0 }} 注</span>
            <p v-if="leg.tickets?.length">票面：{{ ticketGrid(leg.tickets) }}</p>
            <p v-if="leg.wheel_numbers?.length">复式：{{ leg.wheel_numbers.join(' / ') }}</p>
            <p v-if="leg.banker_numbers?.length">胆码：{{ leg.banker_numbers.join(' / ') }}</p>
            <p v-if="leg.drag_numbers?.length">拖码：{{ leg.drag_numbers.join(' / ') }}</p>
          </div>
        </div>
      </div>

      <div class="trust-card">
        <h4>信任策略</h4>
        <div class="trust-grid">
          <div v-for="item in purchasePlan.trusted_strategies || []" :key="item.strategy_id" class="trust-item">
            <strong>{{ item.display_name }}</strong>
            <span>{{ groupLabel(item.group) }} / {{ kindLabel(item.kind) }}</span>
            <span>avg {{ Number(item.average_hits || 0).toFixed(4) }}</span>
            <p>{{ item.numbers.join(' / ') }}</p>
          </div>
        </div>
      </div>

      <div class="history-card">
        <h4>历史收益回放</h4>
        <div class="history-grid">
          <div class="stat-card">
            <span>总成本</span>
            <strong>{{ purchasePlan.historical_backtest?.total_cost }} 元</strong>
          </div>
          <div class="stat-card">
            <span>总返奖</span>
            <strong>{{ purchasePlan.historical_backtest?.total_payout }} 元</strong>
          </div>
          <div class="stat-card">
            <span>净收益</span>
            <strong>{{ purchasePlan.historical_backtest?.net_profit }} 元</strong>
          </div>
          <div class="stat-card">
            <span>ROI</span>
            <strong>{{ purchasePlan.historical_backtest?.roi }}</strong>
          </div>
        </div>
      </div>

      <div class="ticket-card">
        <h4>投注票面</h4>
        <div class="ticket-grid">
          <div v-for="ticket in purchasePlan.tickets || []" :key="ticket.index" class="ticket-item">
            <strong>#{{ ticket.index }}</strong>
            <p>{{ ticket.numbers.join(' / ') }}</p>
          </div>
        </div>
      </div>
    </template>
  </article>
</template>

<script setup>
import { computed } from 'vue'
import { groupLabel, kindLabel } from '../utils/lotteryDisplay'

const props = defineProps({
  purchasePlan: {
    type: Object,
    default: null
  }
})

const portfolioLegs = computed(() => props.purchasePlan?.plan_structure?.portfolio_legs || [])

const reviewRows = computed(() => {
  const review = props.purchasePlan?.play_size_review || props.purchasePlan?.planner?.play_size_review || {}
  return Object.entries(review).map(([key, value]) => ({ key, value }))
})

const ticketGrid = (tickets) =>
  (tickets || [])
    .map((ticket) => Array.isArray(ticket) ? ticket.join(' / ') : String(ticket))
    .join(' | ')
</script>

<style scoped>
.panel,
.planner-card,
.history-card,
.ticket-card,
.trust-card,
.portfolio-card {
  display: grid;
  gap: 0.9rem;
}

.panel {
  padding: 1.15rem;
  border-radius: 1.3rem;
  background: rgba(255, 251, 244, 0.94);
  border: 1px solid rgba(31, 28, 24, 0.1);
}

.panel-header,
.card-top {
  display: flex;
  justify-content: space-between;
  gap: 0.8rem;
}

.eyebrow,
.rationale,
.ticket-item p,
.portfolio-item p,
.stat-card span,
.trust-item span {
  margin: 0;
  color: var(--lottery-muted, #6e675f);
}

.status-pill,
.pill,
.tag {
  display: inline-flex;
  align-items: center;
  padding: 0.32rem 0.7rem;
  border-radius: 999px;
  font-size: 0.76rem;
}

.status-pill.ready,
.pill,
.tag.primary {
  background: var(--lottery-ink, #1d1b19);
  color: #fff;
}

.tag.core {
  background: rgba(15, 118, 110, 0.84);
  color: #fff;
}

.status-pill.skipped,
.tag.hedge {
  background: rgba(196, 140, 76, 0.14);
  color: #8b5a23;
}

.status-pill.unsupported,
.tag.avoid {
  background: rgba(160, 55, 55, 0.1);
  color: #8f3434;
}

.empty-state,
.planner-card,
.history-card,
.ticket-card,
.trust-card,
.portfolio-card {
  padding: 0.95rem;
  border-radius: 1rem;
  background: rgba(255, 255, 255, 0.72);
}

.stats-grid,
.history-grid,
.trust-grid,
.ticket-grid,
.portfolio-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr));
  gap: 0.7rem;
}

.stat-card,
.trust-item,
.portfolio-item,
.ticket-item {
  display: grid;
  gap: 0.35rem;
  padding: 0.85rem;
  border-radius: 0.95rem;
  background: rgba(246, 243, 236, 0.88);
}

.tag-block {
  display: flex;
  flex-wrap: wrap;
  gap: 0.55rem;
}
</style>
