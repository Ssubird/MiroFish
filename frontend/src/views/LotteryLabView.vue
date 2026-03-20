<template>
  <div class="lottery-shell">
    <header class="app-header">
      <div class="header-left">
        <button type="button" class="brand-btn" @click="router.push('/')">MIROFISH</button>
        <div class="page-copy">
          <span class="page-label">ZIWEI HAPPY 8</span>
          <strong>市场持续世界实验台</strong>
        </div>
      </div>

      <div class="header-center">
        <div class="view-switcher">
          <button
            v-for="mode in VIEW_MODES"
            :key="mode.id"
            type="button"
            class="switch-btn"
            :class="{ active: viewMode === mode.id }"
            @click="viewMode = mode.id"
          >
            {{ mode.label }}
          </button>
        </div>
      </div>

      <div class="header-right">
        <div class="workflow-step">
          <span class="step-num">{{ latestPrediction?.predicted_period || sessionRecord?.progress?.awaiting_period || '-' }}</span>
          <span class="step-name">{{ phaseLabel(sessionRecord?.current_phase) }}</span>
        </div>
        <div class="step-divider"></div>
        <span class="status-indicator" :class="statusClass">
          <span class="dot"></span>
          {{ statusText }}
        </span>
      </div>
    </header>

    <div class="summary-strip">
      <span>会话 {{ sessionRecord?.session_id || '-' }}</span>
      <span>可见截止 {{ visibleThroughPeriod || latestPrediction?.visible_through_period || '-' }}</span>
      <span>预测目标 {{ latestPrediction?.predicted_period || '-' }}</span>
      <span>当前模型 {{ activeModelName || selectedModelName || '-' }}</span>
    </div>

    <div v-if="error && !errorDismissed" class="error-banner">
      <span>{{ error }}</span>
      <button type="button" class="error-dismiss" @click="errorDismissed = true">&times;</button>
    </div>

    <main class="content-area">
      <div class="panel-wrapper left" :style="leftPanelStyle">
        <LotteryWorldCanvasStage
          :graph="worldGraph"
          :selected-node-id="selectedGraphNodeId"
          :recent-draw-stats="recentDrawStats"
          :selected-number="selectedNumber"
          :session-status="statusText"
          :predicted-period="latestPrediction?.predicted_period || ''"
          :expanded="viewMode === 'graph'"
          @toggle-maximize="togglePrimaryPane('graph')"
          @select-node="selectedGraphNodeId = $event"
          @select-number="selectedNumber = $event"
        />
      </div>

      <div class="panel-wrapper right" :style="rightPanelStyle">
        <LotteryWorldWorkbench
          :workbench-mode="workbenchMode"
          :expanded="viewMode === 'workbench'"
          :summary="workbenchSummary"
          :control-props="controlPanelProps"
          :inspector-props="inspectorProps"
          @toggle-maximize="togglePrimaryPane('workbench')"
          @update:workbenchMode="workbenchMode = $event"
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
          @update:executionBinding="setExecutionOverride($event.scope, $event.key, $event.profileId)"
          @reset:executionBindings="resetExecutionOverrides()"
          @refresh="refreshWorld"
          @reset="resetWorld"
          @interview="submitInterview"
          @update:agentId="worldInterviewAgentId = $event"
          @update:prompt="worldInterviewPrompt = $event"
          @view-details="openModal"
        />
      </div>
    </main>

    <LotteryTextModal
      v-model:visible="modalVisible"
      :title="modalTitle"
      :content="modalContent"
      :format="modalFormat"
    />
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import LotteryTextModal from '../components/LotteryTextModal.vue'
import LotteryWorldCanvasStage from '../components/LotteryWorldCanvasStage.vue'
import LotteryWorldWorkbench from '../components/LotteryWorldWorkbench.vue'
import { useLotteryWorldStudio } from '../composables/useLotteryWorldStudio'
import { phaseLabel } from '../utils/lotteryDisplay'

const VIEW_MODES = [
  { id: 'graph', label: '图谱' },
  { id: 'split', label: '双栏' },
  { id: 'workbench', label: '工作台' }
]

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
  executionRegistry,
  executionOverrides,
  resolvedExecutionBindings,
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
  lastInterview,
  selectedGraphNode,
  selectedNumberDetail,
  worldInterviewAgentId,
  worldInterviewPrompt,
  worldInterviewBusy,
  canAdvance,
  setExecutionOverride,
  resetExecutionOverrides,
  syncKuzuGraph,
  advanceWorld,
  resetWorld,
  refreshWorld,
  submitInterview,
  probeSelectedModel
} = useLotteryWorldStudio()

const errorDismissed = ref(false)
const modalVisible = ref(false)
const modalTitle = ref('')
const modalContent = ref('')
const modalFormat = ref('text')
const viewMode = ref('split')
const workbenchMode = ref('split')

const sessionRecord = computed(() => session.value?.session || null)
const statusClass = computed(() => {
  if (error.value || sessionRecord.value?.status === 'failed') return 'error'
  if (running.value || busy.value) return 'processing'
  if (sessionRecord.value?.status === 'await_result') return 'completed'
  return 'ready'
})
const statusText = computed(() => {
  if (error.value || sessionRecord.value?.status === 'failed') return '失败'
  if (running.value || busy.value) return '运行中'
  if (sessionRecord.value?.status === 'await_result') return '等待开奖'
  return '就绪'
})
const leftPanelStyle = computed(() => {
  if (viewMode.value === 'graph') return { width: '100%', opacity: 1, transform: 'translateX(0)' }
  if (viewMode.value === 'workbench') return { width: '0%', opacity: 0, transform: 'translateX(-24px)' }
  return { width: '50%', opacity: 1, transform: 'translateX(0)' }
})
const rightPanelStyle = computed(() => {
  if (viewMode.value === 'workbench') return { width: '100%', opacity: 1, transform: 'translateX(0)' }
  if (viewMode.value === 'graph') return { width: '0%', opacity: 0, transform: 'translateX(24px)' }
  return { width: '50%', opacity: 1, transform: 'translateX(0)' }
})
const workbenchSummary = computed(() => ({
  sessionId: sessionRecord.value?.session_id || '',
  phase: phaseLabel(sessionRecord.value?.current_phase),
  selectedStrategies: selectedStrategyIds.value.length,
  timelineCount: worldTimeline.value?.total || 0,
  activeModel: activeModelName.value || selectedModelName.value || ''
}))
const controlPanelProps = computed(() => ({
  strategies: availableStrategies.value,
  selectedIds: selectedStrategyIds.value,
  budgetYuan: budgetYuan.value,
  llmParallelism: llmParallelism.value,
  agentDialogueRounds: agentDialogueRounds.value,
  visibleThroughPeriod: visibleThroughPeriod.value,
  historyPeriods: historyPeriods.value,
  liveInterviewEnabled: liveInterviewEnabled.value,
  llmModels: llmModels.value,
  selectedModelName: selectedModelName.value,
  modelProbeResult: modelProbeResult.value,
  modelListStatus: modelListStatus.value,
  llmModelLoading: llmModelLoading.value,
  executionCatalog: executionRegistry.value,
  executionOverrides: executionOverrides.value,
  resolvedExecutionBindings: resolvedExecutionBindings.value,
  sessionAgents: sessionRecord.value?.agents || [],
  runtimeReadiness: runtimeReadiness.value,
  runtimeReadinessLoading: runtimeReadinessLoading.value,
  graphSyncing: graphSyncing.value,
  kuzuGraphStatus: kuzuGraphStatus.value,
  runMessage: runMessage.value,
  busy: busy.value,
  running: running.value,
  canAdvance: canAdvance.value
}))
const inspectorProps = computed(() => ({
  sessionData: session.value,
  latestPrediction: latestPrediction.value,
  latestPurchasePlan: latestPurchasePlan.value,
  latestSettlement: latestSettlement.value,
  lastInterview: lastInterview.value,
  selectedGraphNode: selectedGraphNode.value,
  selectedNumberDetail: selectedNumberDetail.value,
  timeline: worldTimeline.value,
  budgetYuan: budgetYuan.value,
  activeModelName: activeModelName.value,
  busy: busy.value,
  interviewBusy: worldInterviewBusy.value,
  liveInterviewEnabled: liveInterviewEnabled.value,
  agentId: worldInterviewAgentId.value,
  prompt: worldInterviewPrompt.value
}))

watch(error, () => {
  errorDismissed.value = false
})

const openModal = ({ title, content, format = 'text' }) => {
  modalTitle.value = title || '详情'
  modalContent.value = content || ''
  modalFormat.value = format
  modalVisible.value = true
}

const togglePrimaryPane = (target) => {
  viewMode.value = viewMode.value === target ? 'split' : target
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
