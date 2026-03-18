import { computed, onBeforeUnmount, ref } from 'vue'

import {
  getCurrentLotteryWorld,
  getLotteryRecentDrawStats,
  getLotteryWorldGraph,
  getLotteryWorldResult,
  getLotteryWorldSession,
  getLotteryWorldTimeline,
  interviewLotteryWorldAgent,
  resetLotteryWorld
} from '../api/lottery'


const WORLD_POLL_INTERVAL_MS = 1200
const STOP_STATUSES = new Set(['idle', 'await_result', 'failed'])


export const useLotteryWorld = (setError) => {
  const worldSession = ref(null)
  const worldTimeline = ref({ items: [], total: 0, offset: 0, limit: 120 })
  const worldResult = ref(null)
  const worldGraph = ref({ nodes: [], edges: [], metrics: {} })
  const recentDrawStats = ref({ numbers: [], hot_numbers: [], cold_numbers: [] })
  const worldLoading = ref(false)
  const worldInterviewBusy = ref(false)
  const worldInterviewAgentId = ref('')
  const worldInterviewPrompt = ref('')
  const pollHandle = ref(null)
  const pollBusy = ref(false)

  const worldAgents = computed(() => worldSession.value?.session?.agents || [])
  const worldSharedMemory = computed(() => worldSession.value?.session?.shared_memory || {})

  const clearWorld = () => {
    stopPolling()
    worldSession.value = null
    worldTimeline.value = { items: [], total: 0, offset: 0, limit: 120 }
    worldResult.value = null
    worldGraph.value = { nodes: [], edges: [], metrics: {} }
    recentDrawStats.value = { numbers: [], hot_numbers: [], cold_numbers: [] }
  }

  const loadWorld = async (sessionId) => {
    if (!sessionId) {
      clearWorld()
      return null
    }
    worldLoading.value = true
    try {
      const [sessionResponse, timelineResponse, graphResponse, statsResponse] = await Promise.all([
        getLotteryWorldSession(sessionId),
        getLotteryWorldTimeline(sessionId, 0, 160, true),
        getLotteryWorldGraph(sessionId),
        getLotteryRecentDrawStats(sessionId)
      ])
      worldSession.value = sessionResponse.data
      worldTimeline.value = timelineResponse.data
      worldGraph.value = graphResponse.data
      recentDrawStats.value = statsResponse.data
      worldResult.value = sessionResponse.data.result_available ? (await getLotteryWorldResult(sessionId)).data : null
      ensureInterviewAgent()
      return snapshot()
    } catch (err) {
      setError(err.message || '读取世界会话失败')
      return null
    } finally {
      worldLoading.value = false
    }
  }

  const loadCurrentWorld = async () => {
    worldLoading.value = true
    try {
      const response = await getCurrentLotteryWorld()
      worldSession.value = response.data
      const sessionId = response.data?.session?.session_id || ''
      if (!sessionId) {
        worldTimeline.value = { items: [], total: 0, offset: 0, limit: 120 }
        worldResult.value = null
        worldGraph.value = { nodes: [], edges: [], metrics: {} }
        recentDrawStats.value = (await getLotteryRecentDrawStats()).data
        return null
      }
      const [timelineResponse, graphResponse, statsResponse] = await Promise.all([
        getLotteryWorldTimeline(sessionId, 0, 160, true),
        getLotteryWorldGraph(sessionId),
        getLotteryRecentDrawStats(sessionId)
      ])
      worldTimeline.value = timelineResponse.data
      worldGraph.value = graphResponse.data
      recentDrawStats.value = statsResponse.data
      worldResult.value = response.data.result_available ? (await getLotteryWorldResult(sessionId)).data : null
      ensureInterviewAgent()
      return snapshot()
    } catch (err) {
      if (String(err.message || '').includes('404')) {
        clearWorld()
        recentDrawStats.value = (await getLotteryRecentDrawStats()).data
        return null
      }
      setError(err.message || '读取当前世界会话失败')
      return null
    } finally {
      worldLoading.value = false
    }
  }

  const refreshWorld = async (sessionId) => loadWorld(sessionId)

  const loadRecentDrawStatsOnly = async (sessionId = '') => {
    worldLoading.value = true
    try {
      recentDrawStats.value = (await getLotteryRecentDrawStats(sessionId || undefined)).data
      return recentDrawStats.value
    } catch (err) {
      setError(err.message || '读取最近号码板失败')
      return null
    } finally {
      worldLoading.value = false
    }
  }

  const resetWorld = async () => {
    worldLoading.value = true
    try {
      await resetLotteryWorld()
      clearWorld()
      recentDrawStats.value = (await getLotteryRecentDrawStats()).data
      return true
    } catch (err) {
      setError(err.message || '清空当前世界状态失败')
      return false
    } finally {
      worldLoading.value = false
    }
  }

  const startPolling = (sessionId, onTick) => {
    stopPolling()
    if (!sessionId) return
    pollHandle.value = window.setInterval(async () => {
      if (pollBusy.value) return
      pollBusy.value = true
      try {
        const next = await loadWorld(sessionId)
        if (!next) return
        onTick?.(next)
        if (STOP_STATUSES.has(next.session?.session?.status)) stopPolling()
      } finally {
        pollBusy.value = false
      }
    }, WORLD_POLL_INTERVAL_MS)
  }

  const stopPolling = () => {
    if (!pollHandle.value) return
    window.clearInterval(pollHandle.value)
    pollHandle.value = null
  }

  const submitWorldInterview = async (sessionId) => {
    if (!sessionId) {
      setError('当前没有世界会话')
      return
    }
    if (!worldInterviewAgentId.value || !worldInterviewPrompt.value.trim()) {
      setError('请选择 agent 并输入追问内容')
      return
    }
    worldInterviewBusy.value = true
    try {
      await interviewLotteryWorldAgent(sessionId, {
        agent_id: worldInterviewAgentId.value,
        prompt: worldInterviewPrompt.value.trim()
      })
      worldInterviewPrompt.value = ''
      await loadWorld(sessionId)
    } catch (err) {
      setError(err.message || '发送追问失败')
    } finally {
      worldInterviewBusy.value = false
    }
  }

  const ensureInterviewAgent = () => {
    if (worldAgents.value.some((item) => item.session_agent_id === worldInterviewAgentId.value)) return
    worldInterviewAgentId.value = worldAgents.value[0]?.session_agent_id || ''
  }

  const snapshot = () => ({
    session: worldSession.value,
    timeline: worldTimeline.value,
    result: worldResult.value,
    graph: worldGraph.value,
    recentDrawStats: recentDrawStats.value
  })

  onBeforeUnmount(stopPolling)

  return {
    worldSession,
    worldTimeline,
    worldResult,
    worldGraph,
    recentDrawStats,
    worldLoading,
    worldInterviewBusy,
    worldInterviewAgentId,
    worldInterviewPrompt,
    worldAgents,
    worldSharedMemory,
    loadWorld,
    loadCurrentWorld,
    loadRecentDrawStatsOnly,
    refreshWorld,
    resetWorld,
    startPolling,
    stopPolling,
    submitWorldInterview,
    snapshot
  }
}
