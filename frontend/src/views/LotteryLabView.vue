<template>
  <div class="world-page">
    <header class="page-header">
      <div>
        <p class="eyebrow">ZIWEI HAPPY 8</p>
        <h1>持续状态世界模拟器</h1>
        <p class="page-copy">
          以 `keno8_predict_data.json` 为唯一数据源，围绕最后一条空号码期持续讨论、收敛、购买、等待开奖、结算复盘。
        </p>
      </div>
      <button type="button" class="home-btn" @click="router.push('/')">返回首页</button>
    </header>

    <div v-if="error" class="error-banner">{{ error }}</div>

    <section class="page-grid">
      <aside class="left-column">
        <LotteryWorldControlPanel
          :strategies="availableStrategies"
          :selected-ids="selectedStrategyIds"
          :budget-yuan="budgetYuan"
          :llm-parallelism="llmParallelism"
          :agent-dialogue-rounds="agentDialogueRounds"
          :live-interview-enabled="liveInterviewEnabled"
          :llm-models="llmModels"
          :selected-model-name="selectedModelName"
          :model-probe-result="modelProbeResult"
          :llm-model-loading="llmModelLoading"
          :run-message="runMessage"
          :busy="busy"
          :can-advance="canAdvance"
          @advance="advanceWorld"
          @probe-model="probeSelectedModel(selectedModelName)"
          @select-all="selectedStrategyIds = availableStrategies.map((item) => item.strategy_id)"
          @toggle-strategy="toggleStrategy"
          @update:budgetYuan="budgetYuan = $event"
          @update:llmParallelism="llmParallelism = $event"
          @update:agentDialogueRounds="agentDialogueRounds = $event"
          @update:liveInterviewEnabled="liveInterviewEnabled = $event"
          @update:selectedModelName="selectedModelName = $event"
        />
      </aside>

      <main class="center-column">
        <LotteryWorldGraph
          :graph="worldGraph"
          :selected-node-id="selectedGraphNodeId"
          @select-node="selectedGraphNodeId = $event"
        />
        <LotteryRecentDrawBoard
          :stats="recentDrawStats"
          :selected-number="selectedNumber"
          @select-number="selectedNumber = $event"
        />
      </main>

      <aside class="right-column">
        <LotteryWorldInspector
          :session-data="session"
          :latest-prediction="latestPrediction"
          :latest-purchase-plan="latestPurchasePlan"
          :latest-settlement="latestSettlement"
          :selected-graph-node="selectedGraphNode"
          :selected-number-detail="selectedNumberDetail"
          :timeline="worldTimeline"
          :budget-yuan="budgetYuan"
          :active-model-name="activeModelName"
          :busy="busy"
          :interview-busy="worldInterviewBusy"
          :live-interview-enabled="liveInterviewEnabled"
          :agent-id="worldInterviewAgentId"
          :prompt="worldInterviewPrompt"
          @refresh="refreshWorld"
          @reset="resetWorld"
          @interview="submitInterview"
          @update:agentId="worldInterviewAgentId = $event"
          @update:prompt="worldInterviewPrompt = $event"
        />
      </aside>
    </section>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'

import LotteryRecentDrawBoard from '../components/LotteryRecentDrawBoard.vue'
import LotteryWorldControlPanel from '../components/LotteryWorldControlPanel.vue'
import LotteryWorldGraph from '../components/LotteryWorldGraph.vue'
import LotteryWorldInspector from '../components/LotteryWorldInspector.vue'
import { useLotteryWorldStudio } from '../composables/useLotteryWorldStudio'

const router = useRouter()
const {
  error,
  busy,
  runMessage,
  budgetYuan,
  llmParallelism,
  agentDialogueRounds,
  liveInterviewEnabled,
  selectedStrategyIds,
  selectedGraphNodeId,
  selectedNumber,
  availableStrategies,
  llmModels,
  selectedModelName,
  modelProbeResult,
  llmModelLoading,
  activeModelName,
  session,
  worldTimeline,
  worldGraph,
  recentDrawStats,
  latestPrediction,
  latestPurchasePlan,
  latestSettlement,
  selectedGraphNode,
  selectedNumberDetail,
  worldInterviewAgentId,
  worldInterviewPrompt,
  worldInterviewBusy,
  canAdvance,
  advanceWorld,
  resetWorld,
  refreshWorld,
  submitInterview,
  probeSelectedModel
} = useLotteryWorldStudio()

const toggleStrategy = (strategyId) => {
  if (selectedStrategyIds.value.includes(strategyId)) {
    selectedStrategyIds.value = selectedStrategyIds.value.filter((item) => item !== strategyId)
    return
  }
  selectedStrategyIds.value = [...selectedStrategyIds.value, strategyId]
}
</script>

<style scoped src="../styles/lottery-world.css"></style>
