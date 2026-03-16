<template>
  <section class="hero-shell">
    <div class="hero-main">
      <button class="ghost-btn home-btn" @click="$emit('home')">返回首页</button>
      <p class="eyebrow">LOTTERY WORLD LAB</p>
      <h1>快乐 8 持续状态预测世界</h1>
      <p class="lead">
        主流程现在是持续世界：读取最新 `keno8_predict_data.json`，锁定最后一条 `numbers=[]` 的期号，
        保留上次世界状态，继续讨论、裁判和购买委员会，再等待开奖与复盘。
      </p>
      <div class="hero-metrics">
        <span>{{ availableCount }} 个 agent</span>
        <span>{{ llmCount }} 个 LLM</span>
        <span>预计请求 {{ estimatedCalls }}</span>
        <span>{{ activeModelName }}</span>
        <span>{{ runtimeMode === 'world_v1' ? '持续世界' : '经典回测' }}</span>
        <span v-if="runtimeMode === 'world_v1'">固定 5 主号 + 3 备号</span>
      </div>
    </div>

    <aside class="hero-side">
      <div class="hero-card">
        <p class="eyebrow">COMMAND CENTER</p>
        <h2>{{ runtimeMode === 'world_v1' ? '本轮同步并推进' : '本轮回测摘要' }}</h2>
        <div class="hero-stats">
          <article>
            <span>{{ runtimeMode === 'world_v1' ? '当前模式' : '回测窗口' }}</span>
            <strong>{{ runtimeMode === 'world_v1' ? '持续世界' : evaluationSize }}</strong>
          </article>
          <article>
            <span>每个 agent 选号</span>
            <strong>{{ pickSize }}</strong>
          </article>
          <article>
            <span>同阶段并发</span>
            <strong>x{{ stageParallelism }}</strong>
          </article>
          <article>
            <span>{{ runtimeMode === 'world_v1' ? '状态保留' : '验证并发' }}</span>
            <strong>{{ runtimeMode === 'world_v1' ? 'ON' : `x${issueParallelism}` }}</strong>
          </article>
          <article>
            <span>实时访谈</span>
            <strong>{{ liveInterviewEnabled ? 'ON' : 'OFF' }}</strong>
          </article>
          <article>
            <span>{{ runtimeMode === 'world_v1' ? '固定预热' : '对话轮数' }}</span>
            <strong>{{ runtimeMode === 'world_v1' ? warmupSize : (dialogueEnabled ? dialogueRounds : 0) }}</strong>
          </article>
        </div>
        <button class="run-btn" :disabled="!canRun || busy" @click="$emit('run')">
          {{ busy ? '运行中...' : (runtimeMode === 'world_v1' ? '同步并推进' : '运行回测') }}
        </button>
        <button class="ghost-btn" :disabled="busy" @click="$emit('refresh')">刷新工作区</button>
      </div>

      <div v-if="llmStatus" class="signal-card">
        <p class="eyebrow">LLM SIGNAL</p>
        <h3>{{ llmStatus.configured ? '模型接入已配置' : '模型接入未配置' }}</h3>
        <p>{{ llmStatus.note }}</p>
        <div class="signal-list">
          <span>默认模型：{{ llmStatus.model || '未设置' }}</span>
          <span>Base URL：{{ llmStatus.base_url || '未设置' }}</span>
          <span>请求间隔：{{ delayMs }} ms</span>
          <span>重试退避：{{ retryBackoffMs }} ms</span>
          <span>瞬时重试：{{ retryCount }}</span>
          <span v-if="runtimeMode !== 'world_v1'">对话轮数：{{ dialogueEnabled ? dialogueRounds : 0 }}</span>
          <span v-if="isLongRun">当前请求较重，页面会持续展示中间状态。</span>
        </div>
      </div>
    </aside>
  </section>
</template>

<script setup>
defineProps({
  busy: { type: Boolean, default: false },
  canRun: { type: Boolean, default: false },
  llmStatus: { type: Object, default: null },
  availableCount: { type: Number, default: 0 },
  llmCount: { type: Number, default: 0 },
  estimatedCalls: { type: Number, default: 0 },
  activeModelName: { type: String, default: '未配置' },
  evaluationSize: { type: Number, default: 3 },
  pickSize: { type: Number, default: 5 },
  dialogueEnabled: { type: Boolean, default: true },
  dialogueRounds: { type: Number, default: 1 },
  retryCount: { type: Number, default: 2 },
  delayMs: { type: Number, default: 0 },
  retryBackoffMs: { type: Number, default: 1500 },
  stageParallelism: { type: Number, default: 1 },
  issueParallelism: { type: Number, default: 1 },
  runtimeMode: { type: String, default: 'legacy' },
  warmupSize: { type: Number, default: 3 },
  liveInterviewEnabled: { type: Boolean, default: true },
  isLongRun: { type: Boolean, default: false }
})

defineEmits(['home', 'refresh', 'run'])
</script>

<style scoped>
.hero-shell,
.hero-metrics,
.hero-stats,
.signal-list {
  display: grid;
  gap: 1rem;
}

.hero-shell {
  grid-template-columns: minmax(0, 1.45fr) minmax(21rem, 26rem);
  align-items: start;
  gap: 1.25rem;
}

.hero-main,
.hero-card,
.signal-card {
  padding: 1.4rem;
  border-radius: 1.7rem;
  border: 1px solid var(--lottery-line, rgba(31, 28, 24, 0.1));
  background: var(--lottery-panel, rgba(255, 251, 244, 0.86));
  box-shadow: var(--lottery-shadow, 0 18px 40px rgba(24, 22, 19, 0.08));
}

.hero-main h1,
.hero-card h2,
.signal-card h3 {
  margin: 0;
  font-family: 'Iowan Old Style', 'Palatino Linotype', 'Noto Serif SC', serif;
}

.eyebrow,
.lead,
.hero-metrics span,
.signal-list span,
.hero-stats span {
  margin: 0;
  font-size: 0.85rem;
  line-height: 1.7;
  color: var(--lottery-muted, #6e675f);
}

.lead {
  max-width: 44rem;
}

.hero-metrics {
  grid-template-columns: repeat(3, max-content);
}

.hero-metrics span,
.signal-list span {
  padding: 0.45rem 0.85rem;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.74);
}

.hero-stats {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.hero-stats article {
  display: grid;
  gap: 0.2rem;
  padding: 0.95rem;
  border-radius: 1.1rem;
  background: rgba(255, 255, 255, 0.72);
}

.hero-stats strong {
  font-size: 1.35rem;
}

.home-btn {
  justify-self: start;
}

.ghost-btn,
.run-btn {
  border: 1px solid var(--lottery-line-strong, rgba(31, 28, 24, 0.16));
  border-radius: 999px;
  padding: 0.8rem 1.05rem;
  font: inherit;
  cursor: pointer;
}

.ghost-btn {
  background: rgba(255, 255, 255, 0.82);
}

.run-btn {
  background: var(--lottery-ink, #1d1b19);
  color: #fff;
}

.ghost-btn:disabled,
.run-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

@media (max-width: 1180px) {
  .hero-shell {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .hero-metrics,
  .hero-stats {
    grid-template-columns: 1fr;
  }
}
</style>
