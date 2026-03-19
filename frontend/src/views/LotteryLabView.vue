<template>
  <div class="world-page">
    <header class="page-header">
      <div>
        <p class="eyebrow">ZIWEI HAPPY 8</p>
        <h1>持续状态世界模拟器</h1>
        <p class="page-copy">
          以 `keno8_predict_data.json` 为唯一开奖数据源，按你选择的可见截止期推进一轮，
          先预测下一期，再在下一次点击时完成复盘并继续预测。
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
          :visible-through-period="visibleThroughPeriod"
          :history-periods="historyPeriods"
          :live-interview-enabled="liveInterviewEnabled"
          :llm-models="llmModels"
          :selected-model-name="selectedModelName"
          :model-probe-result="modelProbeResult"
          :model-list-status="modelListStatus"
          :llm-model-loading="llmModelLoading"
          :runtime-readiness="runtimeReadiness"
          :runtime-readiness-loading="runtimeReadinessLoading"
          :graph-syncing="graphSyncing"
          :kuzu-graph-status="kuzuGraphStatus"
          :run-message="runMessage"
          :busy="busy"
          :running="running"
          :can-advance="canAdvance"
          @advance="advanceWorld"
          @sync-kuzu="syncKuzuGraph"
          @load-models="loadModels"
          @probe-model="probeSelectedModel(selectedModelName)"
          @select-all="selectedStrategyIds = availableStrategies.map((item) => item.strategy_id)"
          @toggle-strategy="toggleStrategy"
          @update:budgetYuan="budgetYuan = $event"
          @update:llmParallelism="llmParallelism = $event"
          @update:agentDialogueRounds="agentDialogueRounds = $event"
          @update:visibleThroughPeriod="visibleThroughPeriod = $event"
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
          @view-details="openModal"
        />
      </aside>
    </section>

    <!-- Global Text Modal -->
    <LotteryTextModal
      v-model:visible="modalVisible"
      :title="modalTitle"
      :content="modalContent"
      :format="modalFormat"
    />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'

import LotteryRecentDrawBoard from '../components/LotteryRecentDrawBoard.vue'
import LotteryTextModal from '../components/LotteryTextModal.vue'
import LotteryWorldControlPanel from '../components/LotteryWorldControlPanel.vue'
import LotteryWorldGraph from '../components/LotteryWorldGraph.vue'
import LotteryWorldInspector from '../components/LotteryWorldInspector.vue'
import { useLotteryWorldStudio } from '../composables/useLotteryWorldStudio'

const router = useRouter()
const {
  error,
  busy,
  running,
  runMessage,
  budgetYuan,
  llmParallelism,
  agentDialogueRounds,
  visibleThroughPeriod,
  historyPeriods,
  liveInterviewEnabled,
  selectedStrategyIds,
  selectedGraphNodeId,
  selectedNumber,
  availableStrategies,
  llmModels,
  selectedModelName,
  modelProbeResult,
  modelListStatus,
  llmModelLoading,
  runtimeReadiness,
  runtimeReadinessLoading,
  graphSyncing,
  kuzuGraphStatus,
  loadModels,
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
  syncKuzuGraph,
  advanceWorld,
  resetWorld,
  refreshWorld,
  submitInterview,
  probeSelectedModel
} = useLotteryWorldStudio()

const modalVisible = ref(false)
const modalTitle = ref('')
const modalContent = ref('')
const modalFormat = ref('text')

const openModal = ({ title, content, format = 'text' }) => {
  modalTitle.value = title || '详情'
  modalContent.value = content || ''
  modalFormat.value = format
  modalVisible.value = true
}

const toggleStrategy = (strategyId) => {
  if (selectedStrategyIds.value.includes(strategyId)) {
    selectedStrategyIds.value = selectedStrategyIds.value.filter((item) => item !== strategyId)
    return
  }
  selectedStrategyIds.value = [...selectedStrategyIds.value, strategyId]
}
</script>

<style scoped src="../styles/lottery-world.css"></style>
