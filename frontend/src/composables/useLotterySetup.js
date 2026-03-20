import { computed, onBeforeUnmount, ref } from 'vue'

import {
  getLotteryModels,
  getLotteryOverview,
  probeLotteryModel,
  syncLotteryGraph
} from '../api/lottery'

const UNCONFIGURED_MODEL_LABEL = '未配置模型'
const MODEL_BOOTSTRAP_RETRY_DELAYS_MS = [0, 1500, 3500, 7000]

const unwrapApiPayload = (response) => {
  if (response?.data && typeof response.data === 'object') return response.data
  return response || {}
}

const wait = (delayMs) => new Promise((resolve) => window.setTimeout(resolve, delayMs))

const normalizeModelEntry = (model) => {
  if (typeof model === 'string') {
    const id = model.trim()
    return id ? { id, label: id } : null
  }
  if (!model || typeof model !== 'object') return null
  const id = String(model.id || model.name || '').trim()
  if (!id) return null
  const providerId = String(model.provider_id || '').trim()
  const label = String(model.label || [providerId, id].filter(Boolean).join(' / ') || id).trim() || id
  return { ...model, id, label }
}

const normalizeModelList = (models) => {
  if (!Array.isArray(models)) return []
  const seen = new Set()
  const rows = []
  for (const model of models) {
    const normalized = normalizeModelEntry(model)
    if (!normalized || seen.has(normalized.id)) continue
    seen.add(normalized.id)
    rows.push(normalized)
  }
  return rows
}

export const useLotterySetup = (setError) => {
  const overview = ref(null)
  const loadingOverview = ref(false)
  const graphSyncing = ref(false)
  const llmModelLoading = ref(false)
  const llmModels = ref([])
  const selectedModelName = ref('')
  const modelProbeResult = ref(null)
  const modelListStatus = ref('')
  let bootstrapToken = 0

  const llmStatus = computed(() => overview.value?.llm_status || null)
  const zepGraphStatus = computed(() => overview.value?.zep_graph_status || null)
  const kuzuGraphStatus = computed(() => overview.value?.kuzu_graph_status || null)
  const availableStrategies = computed(() => overview.value?.available_strategies || [])

  const loadOverview = async (onLoaded = null) => {
    loadingOverview.value = true
    try {
      const payload = unwrapApiPayload(await getLotteryOverview())
      overview.value = payload
      if (!selectedModelName.value) {
        selectedModelName.value = payload?.llm_status?.model || ''
      }
      if (onLoaded) onLoaded(payload)
      return payload
    } catch (err) {
      setError(err.message || '读取工作区概览失败')
      return null
    } finally {
      loadingOverview.value = false
    }
  }

  const loadModels = async (options = {}) => {
    const { silent = false } = options
    if (llmModelLoading.value) return false
    llmModelLoading.value = true
    modelProbeResult.value = null
    if (!silent) modelListStatus.value = ''
    try {
      const payload = unwrapApiPayload(await getLotteryModels())
      const models = normalizeModelList(payload.models)
      const current = String(selectedModelName.value || payload.default_model || '').trim()
      if (current && !models.some((item) => item.id === current)) {
        models.unshift({ id: current, label: current })
      }
      llmModels.value = models
      if (!selectedModelName.value) {
        selectedModelName.value = current
      }
      modelListStatus.value = models.length ? `已加载 ${models.length} 个模型` : '模型接口返回了空列表'
      return models.length > 0 || Boolean(current)
    } catch (err) {
      modelListStatus.value = silent ? '模型服务启动中，正在自动重试...' : ''
      if (!silent) {
        setError(err.message || '读取模型列表失败')
      }
      return false
    } finally {
      llmModelLoading.value = false
    }
  }

  const bootstrapModels = async () => {
    if (llmModels.value.length) return true
    const currentToken = bootstrapToken + 1
    bootstrapToken = currentToken
    for (const delayMs of MODEL_BOOTSTRAP_RETRY_DELAYS_MS) {
      if (currentToken !== bootstrapToken) return false
      if (delayMs > 0) {
        await wait(delayMs)
      }
      const ready = await loadModels({ silent: true })
      if (ready) return true
    }
    if (!llmModels.value.length) {
      modelListStatus.value = '模型服务暂未就绪，可稍后手动重试。'
    }
    return false
  }

  const probeSelectedModel = async (modelName) => {
    if (!modelName || modelName === UNCONFIGURED_MODEL_LABEL) {
      setError('当前没有可测试的模型')
      return
    }
    llmModelLoading.value = true
    modelProbeResult.value = null
    try {
      await probeLotteryModel(modelName)
      modelProbeResult.value = { ok: true, message: `${modelName} 测试通过` }
    } catch (err) {
      modelProbeResult.value = { ok: false, message: err.message || `${modelName} 测试失败` }
    } finally {
      llmModelLoading.value = false
    }
  }

  const syncGraph = async (mode, force, onLoaded = null) => {
    graphSyncing.value = true
    try {
      const payload = unwrapApiPayload(await syncLotteryGraph(mode, force))
      await loadOverview(onLoaded)
      return payload
    } catch (err) {
      setError(err.message || '同步图谱失败')
      return null
    } finally {
      graphSyncing.value = false
    }
  }

  onBeforeUnmount(() => {
    bootstrapToken += 1
  })

  return {
    overview,
    loadingOverview,
    graphSyncing,
    llmModelLoading,
    llmModels,
    selectedModelName,
    modelProbeResult,
    modelListStatus,
    llmStatus,
    zepGraphStatus,
    kuzuGraphStatus,
    availableStrategies,
    loadOverview,
    loadModels,
    bootstrapModels,
    probeSelectedModel,
    syncGraph
  }
}
