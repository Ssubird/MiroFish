import { computed, onMounted, ref, watch } from 'vue'

import { advanceLotteryWorld, runLotteryBacktest } from '../api/lottery'
import { useLotterySetup } from './useLotterySetup'
import { useLotteryWorld } from './useLotteryWorld'
import { runtimeLabel } from '../utils/lotteryDisplay'


const FIXED_WORLD_WARMUP = 3
const DEFAULT_GRAPH_MODE = 'local'
const DEFAULT_RUNTIME_MODE = 'world_v2_market'
const LEGACY_RUNTIME_MODE = 'legacy'
const ACTIVE_WORLD_STATUSES = new Set(['queued', 'running'])
const WORLD_GRAPH_LABEL = '内置世界上下文'


const worldRunningMessage = (longRun) => (
  longRun
    ? '持续世界正在推进：会先检查上一期是否可结算，再进入当前目标期的市场摘要、购买人格和最终预测。'
    : '持续世界正在推进当前目标期。'
)

const isPersistentWorldMode = (mode) => mode !== LEGACY_RUNTIME_MODE


export const useLotteryLab = () => {
  const backtest = ref(null)
  const error = ref('')
  const runStatus = ref(null)
  const runningBacktest = ref(false)
  const evaluationSize = ref(3)
  const pickSize = ref(5)
  const llmDelayMs = ref(0)
  const llmParallelism = ref(8)
  const issueParallelism = ref(1)
  const llmRetryCount = ref(2)
  const llmRetryBackoffMs = ref(1500)
  const agentDialogueEnabled = ref(true)
  const agentDialogueRounds = ref(1)
  const runtimeMode = ref(DEFAULT_RUNTIME_MODE)
  const warmupSize = ref(FIXED_WORLD_WARMUP)
  const liveInterviewEnabled = ref(true)
  const budgetYuan = ref(50)
  const selectedStrategyIds = ref([])
  const selectedStrategyId = ref('')
  const graphMode = ref(DEFAULT_GRAPH_MODE)

  const setError = (message) => {
    error.value = message
  }

  const setup = useLotterySetup(setError)
  const world = useLotteryWorld(setError)

  const busy = computed(() => (
    setup.loadingOverview.value
    || runningBacktest.value
    || setup.graphSyncing.value
    || world.worldLoading.value
  ))
  const leaderboard = computed(() => backtest.value?.leaderboard || [])
  const processTrace = computed(() => backtest.value?.process_trace || [])
  const evaluation = computed(() => backtest.value?.evaluation || null)
  const pendingPrediction = computed(() => (
    backtest.value?.pending_prediction || backtest.value?.pending_prediction_partial || null
  ))
  const reportArtifacts = computed(() => backtest.value?.report_artifacts || null)
  const coordinationTrace = computed(() => pendingPrediction.value?.coordination_trace || [])
  const allStrategyIds = computed(() => setup.availableStrategies.value.map((item) => item.strategy_id))
  const requestZepGraphId = computed(() => (
    graphMode.value === 'zep' ? setup.zepGraphStatus.value?.graph_id || undefined : undefined
  ))
  const graphReady = computed(() => {
    if (isPersistentWorldMode(runtimeMode.value)) return true
    if (graphMode.value === 'zep') return Boolean(setup.zepGraphStatus.value?.available)
    if (graphMode.value === 'kuzu') return Boolean(setup.kuzuGraphStatus.value?.available)
    return true
  })
  const selectedLLMCount = computed(() => (
    setup.availableStrategies.value.filter(
      (item) => item.kind === 'llm' && selectedStrategyIds.value.includes(item.strategy_id)
    ).length
  ))
  const estimatedLLMCalls = computed(() => {
    if (isPersistentWorldMode(runtimeMode.value)) {
      const llmStrategies = selectedLLMCount.value
      const socialCalls = 1
      const purchaseCalls = 4
      const rounds = agentDialogueEnabled.value ? Math.max(agentDialogueRounds.value, 1) : 1
      const debateCalls = rounds * Math.max(llmStrategies, 1)
      const debateSummaries = rounds
      return llmStrategies + socialCalls + purchaseCalls + debateCalls + debateSummaries
    }
    const pendingRuns = setup.overview.value?.pending_draws ? 1 : 0
    const periods = evaluationSize.value + pendingRuns
    const llmStrategies = selectedLLMCount.value
    const rounds = agentDialogueEnabled.value ? agentDialogueRounds.value : 0
    return (llmStrategies * (1 + rounds)) * periods
  })
  const isLongRun = computed(() => estimatedLLMCalls.value >= 40)
  const activeModelName = computed(() => (
    setup.selectedModelName.value || setup.llmStatus.value?.model || '未配置'
  ))
  const canRunBacktest = computed(() => !busy.value && graphReady.value && selectedStrategyIds.value.length > 0)
  const selectedStrategy = computed(() => (
    leaderboard.value.find((item) => item.strategy_id === selectedStrategyId.value)
    || leaderboard.value[0]
    || null
  ))
  const requestStrategyIds = computed(() => [...selectedStrategyIds.value])
  const graphStatuses = computed(() => ({
    zep: setup.zepGraphStatus.value || {},
    kuzu: setup.kuzuGraphStatus.value || {},
    local: { available: true, graph_id: 'memory-only' }
  }))
  const graphLabel = computed(() => {
    if (isPersistentWorldMode(runtimeMode.value)) return WORLD_GRAPH_LABEL
    if (graphMode.value === 'zep') return `Zep / ${requestZepGraphId.value || '未同步'}`
    if (graphMode.value === 'kuzu') return `Kuzu / ${setup.kuzuGraphStatus.value?.graph_id || '未同步'}`
    return 'Local'
  })
  const worldSessionId = computed(() => (
    world.worldSession.value?.session?.session_id || backtest.value?.world_session?.session_id || ''
  ))

  const syncSelectedStrategies = () => {
    const availableIds = new Set(allStrategyIds.value)
    const next = selectedStrategyIds.value.filter((id) => availableIds.has(id))
    selectedStrategyIds.value = next.length ? next : [...allStrategyIds.value]
  }

  const updateRunStatus = (state, startedAt, message, response = null) => {
    const finishedAt = state === 'running' ? null : Date.now()
    const runtime = response?.data?.evaluation?.runtime_mode || runtimeMode.value
    const summary = isPersistentWorldMode(runtime)
      ? `${runtimeLabel(runtime)} / 持续世界 / 同阶段并发 x${llmParallelism.value}`
      : [
          runtimeLabel(runtime),
          `回测 ${evaluationSize.value} 期`,
          `同阶段并发 x${llmParallelism.value}`,
          `验证并发 x${issueParallelism.value}`
        ].join(' / ')
    if (response?.data?.leaderboard || response?.data?.pending_prediction || response?.data?.pending_prediction_partial) {
      backtest.value = response.data
    }
    runStatus.value = {
      state,
      startedAt,
      finishedAt,
      elapsedMs: finishedAt ? finishedAt - startedAt : 0,
      summary,
      message
    }
  }

  const updateWorldRunStatus = (startedAt, snapshot) => {
    const session = snapshot?.session?.session
    const result = snapshot?.result
    if (!session) return
    const total = Number(snapshot?.timeline?.total || 0)
    const requests = Number(session.request_metrics?.send_message || 0)
    const middle = Array.isArray(session.latest_issue_summary?.primary_numbers)
      ? session.latest_issue_summary.primary_numbers.join('-')
      : ''
    const detail = [
      `阶段 ${session.current_phase || 'idle'}`,
      `事件 ${total}`,
      `LLM 请求 ${requests}`,
      middle ? `中间结论 ${middle}` : ''
    ].filter(Boolean).join(' / ')
    if (result) backtest.value = result
    if (ACTIVE_WORLD_STATUSES.has(session.status)) {
      error.value = ''
    updateRunStatus('running', startedAt, `涓栫晫鎺ㄨ繘涓細${detail}`)
      updateRunStatus('running', startedAt, `世界推进中：${detail}`)
      return
    }
    if (session.status === 'await_result' || session.status === 'idle') {
      updateRunStatus('success', startedAt, `世界状态已更新：${detail}`, { data: result || {} })
      runningBacktest.value = false
      return
    }
    if (session.status === 'failed') {
      error.value = session.error?.message || '持续世界执行失败'
      updateRunStatus('error', startedAt, session.error?.message || `世界推进失败：${detail}`, { data: result || {} })
      runningBacktest.value = false
      return
    }
    updateRunStatus('running', startedAt, `世界推进中：${detail}`)
  }

  const buildRequestPayload = () => {
    const worldMode = isPersistentWorldMode(runtimeMode.value)
    return {
      evaluation_size: evaluationSize.value,
      pick_size: pickSize.value,
      llm_request_delay_ms: llmDelayMs.value,
      llm_parallelism: llmParallelism.value,
      issue_parallelism: issueParallelism.value,
      llm_retry_count: llmRetryCount.value,
      llm_retry_backoff_ms: llmRetryBackoffMs.value,
      agent_dialogue_enabled: agentDialogueEnabled.value,
      agent_dialogue_rounds: agentDialogueRounds.value,
      llm_model_name: setup.selectedModelName.value || undefined,
      graph_mode: worldMode ? 'local' : graphMode.value,
      zep_graph_id: worldMode ? undefined : requestZepGraphId.value,
      strategy_ids: requestStrategyIds.value,
      runtime_mode: runtimeMode.value,
      warmup_size: warmupSize.value,
      live_interview_enabled: liveInterviewEnabled.value,
      budget_yuan: budgetYuan.value,
      session_id: worldSessionId.value || undefined
    }
  }

  const runBacktest = async () => {
    if (!setup.availableStrategies.value.length) {
      error.value = '工作区概览尚未加载成功，请先刷新。'
      return
    }
    if (!selectedStrategyIds.value.length) {
      error.value = '至少选择一个 agent 后再运行。'
      return
    }
    if (!isPersistentWorldMode(runtimeMode.value) && !graphReady.value) {
      error.value = graphMode.value === 'kuzu' ? '当前 Kuzu 图谱尚未同步。' : '当前 Zep 图谱暂不可用。'
      return
    }
    const startedAt = Date.now()
    runningBacktest.value = true
    error.value = ''
    world.stopPolling()
    updateRunStatus(
      'running',
      startedAt,
      isPersistentWorldMode(runtimeMode.value)
        ? worldRunningMessage(isLongRun.value)
        : '后端正在执行经典回测。'
    )
    try {
      const payload = buildRequestPayload()
      if (isPersistentWorldMode(runtimeMode.value)) {
        const response = await advanceLotteryWorld(payload)
        const sessionId = response.data.world_session?.session_id || ''
        const snapshot = await world.loadWorld(sessionId)
        if (snapshot) updateWorldRunStatus(startedAt, snapshot)
        world.startPolling(sessionId, (next) => updateWorldRunStatus(startedAt, next))
        return
      }
      const response = await runLotteryBacktest(payload)
      updateRunStatus('success', startedAt, '经典回测已完成。', response)
      await world.loadWorld(response.data.world_session?.session_id || '')
      runningBacktest.value = false
    } catch (err) {
      world.stopPolling()
      runningBacktest.value = false
      error.value = err.message || '执行失败'
      updateRunStatus('error', startedAt, err.message || '执行失败')
    }
  }

  const reloadAll = async () => {
    await setup.loadOverview(syncSelectedStrategies)
    await setup.loadModels()
    const snapshot = worldSessionId.value
      ? await world.loadWorld(worldSessionId.value)
      : await world.loadCurrentWorld()
    if (ACTIVE_WORLD_STATUSES.has(snapshot?.session?.session?.status)) {
      const startedAt = new Date(snapshot.session.session.created_at || Date.now()).getTime()
      runningBacktest.value = true
      updateWorldRunStatus(startedAt, snapshot)
      world.startPolling(snapshot.session.session.session_id, (next) => updateWorldRunStatus(startedAt, next))
    }
    if (snapshot?.result) backtest.value = snapshot.result
  }

  const resetWorldState = async () => {
    const ok = await world.resetWorld()
    if (!ok) return
    backtest.value = null
    runStatus.value = null
    runningBacktest.value = false
    error.value = ''
  }

  watch(leaderboard, (items) => {
    if (!items.length) {
      selectedStrategyId.value = ''
      return
    }
    if (!items.some((item) => item.strategy_id === selectedStrategyId.value)) {
      selectedStrategyId.value = items[0].strategy_id
    }
  })

  watch(runtimeMode, (mode) => {
    if (!isPersistentWorldMode(mode)) return
    warmupSize.value = FIXED_WORLD_WARMUP
    pickSize.value = 5
    issueParallelism.value = 1
    liveInterviewEnabled.value = true
  })

  onMounted(reloadAll)

  return {
    overview: setup.overview,
    backtest,
    worldSession: world.worldSession,
    worldTimeline: world.worldTimeline,
    worldResult: world.worldResult,
    worldSharedMemory: world.worldSharedMemory,
    worldAgents: world.worldAgents,
    error,
    runStatus,
    llmModels: setup.llmModels,
    selectedModelName: setup.selectedModelName,
    modelProbeResult: setup.modelProbeResult,
    selectedStrategyIds,
    selectedStrategyId,
    graphMode,
    evaluationSize,
    pickSize,
    llmDelayMs,
    llmParallelism,
    issueParallelism,
    llmRetryCount,
    llmRetryBackoffMs,
    agentDialogueEnabled,
    agentDialogueRounds,
    runtimeMode,
    warmupSize,
    liveInterviewEnabled,
    budgetYuan,
    worldInterviewAgentId: world.worldInterviewAgentId,
    worldInterviewPrompt: world.worldInterviewPrompt,
    busy,
    graphSyncing: setup.graphSyncing,
    llmModelLoading: setup.llmModelLoading,
    worldLoading: world.worldLoading,
    worldInterviewBusy: world.worldInterviewBusy,
    llmStatus: setup.llmStatus,
    availableStrategies: setup.availableStrategies,
    leaderboard,
    processTrace,
    evaluation,
    pendingPrediction,
    reportArtifacts,
    coordinationTrace,
    graphStatuses,
    graphLabel,
    selectedLLMCount,
    estimatedLLMCalls,
    isLongRun,
    activeModelName,
    canRunBacktest,
    selectedStrategy,
    loadModels: setup.loadModels,
    probeSelectedModel: setup.probeSelectedModel,
    syncGraph: setup.syncGraph,
    runBacktest,
    resetWorldState,
    refreshWorld: world.refreshWorld,
    submitWorldInterview: () => world.submitWorldInterview(worldSessionId.value),
    reloadAll
  }
}
