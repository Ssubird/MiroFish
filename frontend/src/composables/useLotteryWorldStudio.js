import { computed, onMounted, ref, watch } from 'vue'

import { advanceLotteryWorld } from '../api/lottery'
import { useLotterySetup } from './useLotterySetup'
import { useLotteryWorld } from './useLotteryWorld'


const DEFAULT_BUDGET_YUAN = 50
const DEFAULT_LLM_PARALLELISM = 8
const DEFAULT_DIALOGUE_ROUNDS = 1


export const useLotteryWorldStudio = () => {
  const error = ref('')
  const running = ref(false)
  const runMessage = ref('')
  const budgetYuan = ref(DEFAULT_BUDGET_YUAN)
  const llmParallelism = ref(DEFAULT_LLM_PARALLELISM)
  const agentDialogueRounds = ref(DEFAULT_DIALOGUE_ROUNDS)
  const liveInterviewEnabled = ref(true)
  const selectedStrategyIds = ref([])
  const selectedGraphNodeId = ref('')
  const selectedNumber = ref(null)

  const setError = (message) => {
    error.value = message
  }

  const setup = useLotterySetup(setError)
  const world = useLotteryWorld(setError)

  const busy = computed(() => setup.loadingOverview.value || setup.llmModelLoading.value || world.worldLoading.value || running.value)
  const availableStrategies = computed(() => setup.availableStrategies.value)
  const session = computed(() => world.worldSession.value?.session || null)
  const currentSessionId = computed(() => session.value?.session_id || '')
  const latestPrediction = computed(() => world.worldResult.value?.pending_prediction || session.value?.latest_prediction || null)
  const latestPurchasePlan = computed(() => session.value?.latest_purchase_plan || latestPrediction.value?.purchase_plan || null)
  const latestSettlement = computed(() => {
    const rows = session.value?.settlement_history || []
    return rows.length ? rows[rows.length - 1] : null
  })
  const graphNodes = computed(() => world.worldGraph.value?.nodes || [])
  const selectedGraphNode = computed(() => graphNodes.value.find((item) => item.id === selectedGraphNodeId.value) || null)
  const recentNumbers = computed(() => world.recentDrawStats.value?.numbers || [])
  const selectedNumberDetail = computed(() => recentNumbers.value.find((item) => item.number === selectedNumber.value) || null)
  const activeModelName = computed(() => setup.selectedModelName.value || setup.llmStatus.value?.model || '')
  const canAdvance = computed(() => !busy.value && sanitizedStrategyIds().length > 0)

  const sanitizedStrategyIds = () => {
    const availableIds = new Set(availableStrategies.value.map((item) => item.strategy_id))
    return selectedStrategyIds.value.filter((item) => availableIds.has(item))
  }

  const syncSelectedStrategies = () => {
    const next = sanitizedStrategyIds()
    selectedStrategyIds.value = next.length ? next : availableStrategies.value.map((item) => item.strategy_id)
  }

  const updateRunMessage = (snapshot) => {
    const activeSession = snapshot?.session?.session
    if (!activeSession) {
      runMessage.value = ''
      running.value = false
      return
    }
    const requestCount = Number(activeSession.request_metrics?.send_message || 0)
    const nodeCount = Number(snapshot.graph?.metrics?.node_count || 0)
    runMessage.value = `状态 ${activeSession.status || '-'} / 阶段 ${activeSession.current_phase || '-'} / LLM 请求 ${requestCount} / 图节点 ${nodeCount}`
    running.value = activeSession.status === 'running'
  }

  const ensureSelections = () => {
    if (!graphNodes.value.some((item) => item.id === selectedGraphNodeId.value)) {
      selectedGraphNodeId.value = graphNodes.value[0]?.id || ''
    }
    if (!recentNumbers.value.some((item) => item.number === selectedNumber.value)) {
      selectedNumber.value = recentNumbers.value[0]?.number ?? null
    }
  }

  const loadAll = async () => {
    await setup.loadOverview(syncSelectedStrategies)
    await setup.loadModels()
    const snapshot = await world.loadCurrentWorld()
    if (snapshot) updateRunMessage(snapshot)
    if (snapshot?.session?.session?.status === 'running') {
      world.startPolling(snapshot.session.session.session_id, updateRunMessage)
    }
    ensureSelections()
  }

  const advanceWorld = async () => {
    if (!canAdvance.value) return
    error.value = ''
    running.value = true
    runMessage.value = '正在同步状态并推进世界模拟...'
    world.stopPolling()
    try {
      const strategyIds = sanitizedStrategyIds()
      selectedStrategyIds.value = [...strategyIds]
      const response = await advanceLotteryWorld({
        strategy_ids: strategyIds,
        llm_model_name: setup.selectedModelName.value || undefined,
        llm_parallelism: llmParallelism.value,
        issue_parallelism: 1,
        agent_dialogue_enabled: agentDialogueRounds.value > 0,
        agent_dialogue_rounds: agentDialogueRounds.value,
        live_interview_enabled: liveInterviewEnabled.value,
        budget_yuan: budgetYuan.value,
        session_id: currentSessionId.value || undefined
      })
      const sessionId = response.data?.world_session?.session_id || ''
      const snapshot = await world.loadWorld(sessionId)
      if (snapshot) updateRunMessage(snapshot)
      if (sessionId) world.startPolling(sessionId, updateRunMessage)
      ensureSelections()
    } catch (err) {
      running.value = false
      runMessage.value = ''
      error.value = err.message || '推进世界失败'
    }
  }

  const resetWorld = async () => {
    const ok = await world.resetWorld()
    if (!ok) return
    running.value = false
    runMessage.value = ''
    selectedGraphNodeId.value = ''
    selectedNumber.value = null
  }

  const refreshWorld = async () => {
    if (!currentSessionId.value) {
      await loadAll()
      return
    }
    const snapshot = await world.refreshWorld(currentSessionId.value)
    if (snapshot) updateRunMessage(snapshot)
    ensureSelections()
  }

  watch(availableStrategies, syncSelectedStrategies)
  watch(graphNodes, ensureSelections)
  watch(recentNumbers, ensureSelections)
  watch(session, (payload) => {
    if (!payload) return
    budgetYuan.value = Number(payload.budget_yuan || budgetYuan.value)
    const chosen = payload.selected_strategy_ids || []
    if (!Array.isArray(chosen) || !chosen.length) return
    selectedStrategyIds.value = [...chosen]
    syncSelectedStrategies()
  })

  onMounted(loadAll)

  return {
    overview: setup.overview,
    error,
    busy,
    running,
    runMessage,
    budgetYuan,
    llmParallelism,
    agentDialogueRounds,
    liveInterviewEnabled,
    selectedStrategyIds,
    selectedGraphNodeId,
    selectedNumber,
    availableStrategies,
    llmModels: setup.llmModels,
    selectedModelName: setup.selectedModelName,
    modelProbeResult: setup.modelProbeResult,
    llmModelLoading: setup.llmModelLoading,
    activeModelName,
    session: world.worldSession,
    worldTimeline: world.worldTimeline,
    worldGraph: world.worldGraph,
    recentDrawStats: world.recentDrawStats,
    latestPrediction,
    latestPurchasePlan,
    latestSettlement,
    selectedGraphNode,
    selectedNumberDetail,
    worldInterviewAgentId: world.worldInterviewAgentId,
    worldInterviewPrompt: world.worldInterviewPrompt,
    worldInterviewBusy: world.worldInterviewBusy,
    canAdvance,
    advanceWorld,
    resetWorld,
    refreshWorld,
    submitInterview: () => world.submitWorldInterview(currentSessionId.value),
    probeSelectedModel: setup.probeSelectedModel
  }
}
