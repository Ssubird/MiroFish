export const GROUP_LABELS = {
  data: '数据组',
  metaphysics: '玄学组',
  hybrid: '混合组',
  purchase: '购买组',
  analyst: '分析组'
}

export const NODE_TYPE_LABELS = {
  agent: 'Agent',
  phase: '阶段',
  debate_round: '讨论轮'
}

export const groupLabel = (group) => GROUP_LABELS[group] || group || '-'

export const kindLabel = (kind) => (kind === 'llm' ? 'LLM' : '规则')

export const runtimeLabel = (mode) => (mode === 'world_v1' ? '持续世界' : '经典回测')

export const nodeTypeLabel = (nodeType) => NODE_TYPE_LABELS[nodeType] || nodeType || '-'

export const phaseLabel = (phase) => {
  const labels = {
    idle: '待命',
    queued: '排队中',
    opening: '开场选号',
    rule_interpretation: '规则摘要',
    public_debate: '公开讨论',
    judge_synthesis: '综合收敛',
    purchase_committee: '购买委员会',
    await_result: '等待开奖',
    settlement: '结果结算',
    postmortem: '复盘修正',
    completed: '已完成',
    failed: '已失败'
  }
  return labels[phase] || phase || '-'
}

export const eventLabel = (type) => {
  const labels = {
    session_started: '会话启动',
    phase_change: '阶段切换',
    agent_registered: '节点创建',
    run_failed: '运行失败',
    prediction_post: '开场选号',
    rule_summary: '规则摘要',
    live_interview: '系统访谈',
    external_interview: '人工追问',
    debate_post: '讨论发言',
    debate_summary: '讨论总结',
    judge_decision: '综合收敛',
    purchase_proposal: '购买提案',
    purchase_decision: '购买定稿'
  }
  return labels[type] || type || '-'
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
