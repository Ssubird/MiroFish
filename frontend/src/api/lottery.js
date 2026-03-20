import service from './index'

const LOTTERY_MODEL_PROBE_TIMEOUT_MS = 180000
const LOTTERY_MODELS_TIMEOUT_MS = 15000
const LOTTERY_WORLD_TIMELINE_LIMIT = 120

export const getLotteryOverview = () => service.get('/api/lottery/overview')

export const getLotteryGraphStatus = () => service.get('/api/lottery/graph/status')

export const syncLotteryGraph = (mode = 'zep', force = false) => {
  return service.post('/api/lottery/graph/sync', { mode, force }, { timeout: 0 })
}

export const getLotteryModels = () => {
  return service.get('/api/lottery/models', { timeout: LOTTERY_MODELS_TIMEOUT_MS })
}

export const getLotteryExecutionRegistry = () => {
  return service.get('/api/lottery/execution/registry')
}

export const probeLotteryModel = (modelName) => {
  return service.post(
    '/api/lottery/models/probe',
    { model_name: modelName },
    { timeout: LOTTERY_MODEL_PROBE_TIMEOUT_MS }
  )
}

export const runLotteryBacktest = (data) => {
  return service.post('/api/lottery/backtest', data, { timeout: 0 })
}

export const startLotteryWorld = (data) => {
  return service.post('/api/lottery/world/start', data, { timeout: 0 })
}

export const advanceLotteryWorld = (data) => {
  return service.post('/api/lottery/world/advance', data, { timeout: 0 })
}

export const getLotteryWorldRuntimeReadiness = () => {
  return service.get('/api/lottery/world/runtime-readiness')
}

export const getCurrentLotteryWorld = () => {
  return service.get('/api/lottery/world/current')
}

export const resetLotteryWorld = () => {
  return service.post('/api/lottery/world/reset', {}, { timeout: 0 })
}

export const getLotteryWorldSession = (sessionId) => {
  return service.get(`/api/lottery/world/${sessionId}`)
}

export const getLotteryWorldTimeline = (
  sessionId,
  offset = 0,
  limit = LOTTERY_WORLD_TIMELINE_LIMIT,
  latest = false
) => {
  return service.get(`/api/lottery/world/${sessionId}/timeline`, {
    params: { offset, limit, latest }
  })
}

export const getLotteryWorldResult = (sessionId) => {
  return service.get(`/api/lottery/world/${sessionId}/result`)
}

export const getLotteryWorldGraph = (sessionId) => {
  return service.get(`/api/lottery/world/${sessionId}/graph`)
}

export const getLotteryRecentDrawStats = (sessionId = '') => {
  return service.get('/api/lottery/world/recent-draw-stats', {
    params: { session_id: sessionId || undefined }
  })
}

export const interviewLotteryWorldAgent = (sessionId, payload) => {
  return service.post(`/api/lottery/world/${sessionId}/interview`, payload, { timeout: 0 })
}
