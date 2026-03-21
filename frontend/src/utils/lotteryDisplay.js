export const GROUP_LABELS = {
  data: '数据组',
  metaphysics: '玄学组',
  hybrid: '混合组',
  social: '市场摘要',
  purchase: '购买层'
}

export const NODE_TYPE_LABELS = {
  agent: 'Agent',
  phase: '阶段',
  debate_round: '讨论轮'
}

export const groupLabel = (group) => GROUP_LABELS[group] || group || '-'

export const kindLabel = (kind) => {
  if (kind === 'llm') return 'LLM'
  if (kind === 'market_synthesis') return '市场综合'
  if (kind === 'official_prediction') return '最终预测'
  return '规则'
}

export const runtimeLabel = (mode) => {
  if (mode === 'world_v2_market') return '购买主线世界'
  if (mode === 'world_v1') return '旧版持续世界'
  return '经典回测'
}

export const nodeTypeLabel = (nodeType) => NODE_TYPE_LABELS[nodeType] || nodeType || '-'

export const phaseLabel = (phase) => {
  const labels = {
    idle: '待命',
    queued: '排队中',
    opening: '开场选题',
    generator_opening: '生成组开盘',
    social_propagation: '市场摘要',
    plan_synthesis: '购买方案收口',
    final_decision: '最终预测',
    public_debate: '公开讨论',
    judge_synthesis: '裁判综合',
    purchase_committee: '购买委员会',
    await_result: '等待开奖',
    settlement: '结果结算',
    postmortem: '复盘总结',
    completed: '已完成',
    failed: '已失败'
  }
  return labels[phase] || phase || '-'
}

export const eventLabel = (type) => {
  const labels = {
    session_started: '会话启动',
    phase_change: '阶段切换',
    agent_registered: '角色注册',
    run_failed: '运行失败',
    prediction_post: '生成组结论',
    rule_summary: '规则摘要',
    live_interview: '系统访谈',
    external_interview: '人工追问',
    debate_post: '公开讨论',
    debate_summary: '讨论总结',
    social_post: '市场发言',
    social_reply: '市场回复',
    purchase_proposal: '购买提案',
    purchase_decision: '购买方案',
    official_prediction: '最终预测'
  }
  return labels[type] || type || '-'
}

export const logLevelLabel = (level) => {
  const labels = {
    info: '信息',
    warning: '警告',
    error: '错误'
  }
  return labels[level] || level || '-'
}

export const shortText = (value, max = 180) => {
  const text = String(value || '').trim()
  if (text.length <= max) return text
  return `${text.slice(0, max)}...`
}

export const formatDurationLabel = (value) => {
  if (value == null) return '-'
  const seconds = Math.max(Math.round(value / 1000), 0)
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const remaining = seconds % 60
  if (hours > 0) return `${hours}h ${minutes}m ${remaining}s`
  return `${minutes}m ${remaining}s`
}
