import { computed, onMounted, ref, watch } from 'vue'

import {
  advanceLotteryWorld,
  getLotteryWorldRuntimeReadiness
} from '../api/lottery'
import { useLotterySetup } from './useLotterySetup'
import { useLotteryWorld } from './useLotteryWorld'


const DEFAULT_BUDGET_YUAN = 50
const DEFAULT_LLM_PARALLELISM = 8
const DEFAULT_DIALOGUE_ROUNDS = 1
const MAX_DIALOGUE_ROUNDS = 5
const ACTIVE_SESSION_STATUSES = new Set(['queued', 'running'])


export const useLotteryWorldStudio = () => {
  const error = ref('')
  const running = ref(false)
  const runMessage = ref('')
  const runtimeReadiness = ref(null)
  const runtimeReadinessLoading = ref(false)
  const budgetYuan = ref(DEFAULT_BUDGET_YUAN)
  const llmParallelism = ref(DEFAULT_LLM_PARALLELISM)
  const agentDialogueRounds = ref(DEFAULT_DIALOGUE_ROUNDS)
  const visibleThroughPeriod = ref('')
  const liveInterviewEnabled = ref(true)
  const selectedStrategyIds = ref([])
  const selectedGraphNodeId = ref('')
  const selectedNumber = ref(null)

  const setError = (message) => {
    error.value = message
  }

  const setup = useLotterySetup(setError)
  const world = useLotteryWorld(setError)

  const loading = computed(() => (
    setup.loadingOverview.value
    || world.worldLoading.value
    || runtimeReadinessLoading.value
  ))
  const busy = computed(() => loading.value || running.value)
  const availableStrategies = computed(() => setup.availableStrategies.value)
  const historyPeriods = computed(() => setup.overview.value?.history_periods || [])
  const kuzuGraphStatus = computed(() => setup.kuzuGraphStatus.value || {})
  const session = computed(() => world.worldSession.value?.session || null)
  const currentSessionId = computed(() => session.value?.session_id || '')
  const latestPrediction = computed(() => (
    world.worldResult.value?.pending_prediction || session.value?.latest_prediction || null
  ))
  const latestPurchasePlan = computed(() => (
    session.value?.latest_purchase_plan || latestPrediction.value?.purchase_recommendation || null
  ))
  const latestSettlement = computed(() => {
    const rows = session.value?.settlement_history || []
    return rows.length ? rows[rows.length - 1] : null
  })
  const graphNodes = computed(() => world.worldGraph.value?.nodes || [])
  const selectedGraphNode = computed(() => (
    graphNodes.value.find((item) => item.id === selectedGraphNodeId.value) || null
  ))
  const recentNumbers = computed(() => world.recentDrawStats.value?.numbers || [])
  const selectedNumberDetail = computed(() => (
    recentNumbers.value.find((item) => item.number === selectedNumber.value) || null
  ))
  const activeModelName = computed(() => setup.selectedModelName.value || setup.llmStatus.value?.model || '')
  const canAdvance = computed(() => (
    !busy.value
    && runtimeReadiness.value?.ready === true
    && sanitizedStrategyIds().length > 0
  ))
  const kuzuSyncRequired = computed(() => (
    !kuzuGraphStatus.value?.available || Boolean(kuzuGraphStatus.value?.is_stale)
  ))

  const sanitizedStrategyIds = () => {
    const availableIds = new Set(availableStrategies.value.map((item) => item.strategy_id))
    return selectedStrategyIds.value.filter((item) => availableIds.has(item))
  }

  const syncSelectedStrategies = () => {
    const next = sanitizedStrategyIds()
    selectedStrategyIds.value = next.length ? next : availableStrategies.value.map((item) => item.strategy_id)
  }

  const clearRunState = () => {
    runMessage.value = ''
    running.value = false
  }

  const loadRuntimeReadiness = async () => {
    runtimeReadinessLoading.value = true
    try {
      const response = await getLotteryWorldRuntimeReadiness()
      runtimeReadiness.value = response.data
    } catch (err) {
      runtimeReadiness.value = null
      setError(err.message || '读取运行前置条件失败')
    } finally {
      runtimeReadinessLoading.value = false
    }
  }

  const updateRunMessage = (snapshot, options = {}) => {
    const { adoptActiveStatus = true } = options
    const activeSession = snapshot?.session?.session
    if (!activeSession || !adoptActiveStatus) {
      clearRunState()
      return
    }

    const requestCount = Number(activeSession.request_metrics?.send_message || 0)
    const nodeCount = Number(snapshot.graph?.metrics?.node_count || 0)
    const progress = activeSession.progress || {}
    const dialogueTotal = Number(progress.dialogue_round_total || 0)
    const dialogueText = dialogueTotal > 0
      ? ` / 讨论 ${progress.dialogue_round_index || 0}/${dialogueTotal}`
      : ''
    runMessage.value = `状态 ${activeSession.status || '-'} / 阶段 ${activeSession.current_phase || '-'}${dialogueText} / LLM 请求 ${requestCount} / 图节点 ${nodeCount}`

    if (activeSession.status === 'failed' && activeSession.error?.message) {
      error.value = activeSession.error.message
    } else if (activeSession.status !== 'failed') {
      error.value = ''
    }

    running.value = ACTIVE_SESSION_STATUSES.has(activeSession.status)
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
    const [, , snapshot] = await Promise.all([
      setup.loadOverview(syncSelectedStrategies),
      loadRuntimeReadiness(),
      world.loadCurrentWorld(),
      setup.loadModels()
    ])
    const sessionId = snapshot?.session?.session?.session_id || ''
    const status = snapshot?.session?.session?.status || ''
    if (snapshot) {
      updateRunMessage(snapshot)
      if (sessionId && ACTIVE_SESSION_STATUSES.has(status)) {
        world.startPolling(sessionId, updateRunMessage)
      } else {
        world.stopPolling()
      }
    } else {
      clearRunState()
      world.stopPolling()
    }
    ensureSelections()
  }

  const loadModels = async () => {
    await setup.loadModels()
  }

  const syncKuzuGraph = async (force = false) => {
    const payload = await setup.syncGraph('kuzu', force, syncSelectedStrategies)
    return Boolean(payload)
  }

  const advanceWorld = async () => {
    if (!canAdvance.value) return
    error.value = ''
    running.value = true
    runMessage.value = '正在按可见截止期推进模拟世界...'
    world.stopPolling()

    try {
      if (kuzuSyncRequired.value) {
        runMessage.value = '姝ｅ湪鍚屾 Kuzu 鍥捐氨...'
        const synced = await syncKuzuGraph(false)
        if (!synced) {
          clearRunState()
          return
        }
        runMessage.value = 'Kuzu 鍥捐氨宸插悓姝ワ紝姝ｅ湪鎺ㄨ繘妯℃嫙涓栫晫...'
      }
      const strategyIds = sanitizedStrategyIds()
      selectedStrategyIds.value = [...strategyIds]
      const response = await advanceLotteryWorld({
        strategy_ids: strategyIds,
        llm_model_name: setup.selectedModelName.value || undefined,
        llm_parallelism: llmParallelism.value,
        issue_parallelism: 1,
        agent_dialogue_enabled: agentDialogueRounds.value > 0,
        agent_dialogue_rounds: Math.min(Math.max(agentDialogueRounds.value, 0), MAX_DIALOGUE_ROUNDS),
        live_interview_enabled: liveInterviewEnabled.value,
        budget_yuan: budgetYuan.value,
        session_id: currentSessionId.value || undefined,
        visible_through_period: visibleThroughPeriod.value || undefined
      })
      const sessionId = response.data?.world_session?.session_id || ''
      const snapshot = await world.loadWorld(sessionId)
      if (snapshot) updateRunMessage(snapshot)
      if (sessionId) world.startPolling(sessionId, updateRunMessage)
      ensureSelections()
    } catch (err) {
      clearRunState()
      error.value = err.message || '推进世界失败'
      await loadRuntimeReadiness()
    }
  }

  const resetWorld = async () => {
    const ok = await world.resetWorld()
    if (!ok) return
    clearRunState()
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
    runtimeReadiness,
    runtimeReadinessLoading,
    graphSyncing: setup.graphSyncing,
    kuzuGraphStatus,
    budgetYuan,
    llmParallelism,
    agentDialogueRounds,
    visibleThroughPeriod,
    liveInterviewEnabled,
    selectedStrategyIds,
    selectedGraphNodeId,
    selectedNumber,
    availableStrategies,
    historyPeriods,
    llmModels: setup.llmModels,
    selectedModelName: setup.selectedModelName,
    modelProbeResult: setup.modelProbeResult,
    modelListStatus: setup.modelListStatus,
    llmModelLoading: setup.llmModelLoading,
    loadModels,
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
    syncKuzuGraph,
    advanceWorld,
    resetWorld,
    refreshWorld,
    submitInterview: () => world.submitWorldInterview(currentSessionId.value),
    probeSelectedModel: setup.probeSelectedModel
  }
}
