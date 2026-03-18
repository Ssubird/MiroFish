import { computed, ref } from 'vue'

import {
  getLotteryModels,
  getLotteryOverview,
  probeLotteryModel,
  syncLotteryGraph
} from '../api/lottery'

const UNCONFIGURED_MODEL_LABEL = '未配置'

const unwrapApiPayload = (response) => {
  if (response?.data && typeof response.data === 'object') return response.data
  return response || {}
}

const normalizeModelEntry = (model) => {
  if (typeof model === 'string') {
    const id = model.trim()
    return id ? { id, label: id } : null
  }
  if (!model || typeof model !== 'object') return null
  const id = String(model.id || model.name || '').trim()
  if (!id) return null
  return { ...model, id, label: String(model.label || id).trim() || id }
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
    } catch (err) {
      setError(err.message || '读取工作区概览失败')
    } finally {
      loadingOverview.value = false
    }
  }

  const loadModels = async () => {
    if (llmModelLoading.value) return
    llmModelLoading.value = true
    modelProbeResult.value = null
    modelListStatus.value = ''
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
    } catch (err) {
      modelListStatus.value = ''
      setError(err.message || '读取模型列表失败')
    } finally {
      llmModelLoading.value = false
    }
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
      await syncLotteryGraph(mode, force)
      await loadOverview(onLoaded)
    } catch (err) {
      setError(err.message || '同步图谱失败')
    } finally {
      graphSyncing.value = false
    }
  }

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
    probeSelectedModel,
    syncGraph
  }
}
