import { computed, ref } from 'vue'

import {
  getLotteryModels,
  getLotteryOverview,
  probeLotteryModel,
  syncLotteryGraph
} from '../api/lottery'

export const useLotterySetup = (setError) => {
  const overview = ref(null)
  const loadingOverview = ref(false)
  const graphSyncing = ref(false)
  const llmModelLoading = ref(false)
  const llmModels = ref([])
  const selectedModelName = ref('')
  const modelProbeResult = ref(null)

  const llmStatus = computed(() => overview.value?.llm_status || null)
  const zepGraphStatus = computed(() => overview.value?.zep_graph_status || null)
  const kuzuGraphStatus = computed(() => overview.value?.kuzu_graph_status || null)
  const availableStrategies = computed(() => overview.value?.available_strategies || [])

  const loadOverview = async (onLoaded = null) => {
    loadingOverview.value = true
    try {
      const response = await getLotteryOverview()
      overview.value = response.data
      if (onLoaded) onLoaded(response.data)
    } catch (err) {
      setError(err.message || '读取工作区失败')
    } finally {
      loadingOverview.value = false
    }
  }

  const loadModels = async () => {
    llmModelLoading.value = true
    modelProbeResult.value = null
    try {
      const response = await getLotteryModels()
      llmModels.value = response.data.models || []
      if (!selectedModelName.value) selectedModelName.value = response.data.default_model || ''
    } catch (err) {
      setError(err.message || '读取模型列表失败')
    } finally {
      llmModelLoading.value = false
    }
  }

  const probeSelectedModel = async (modelName) => {
    if (!modelName || modelName === '未配置') {
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
