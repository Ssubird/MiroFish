<template>
  <div class="control-grid">
    <article class="control-card accent">
      <div class="card-head">
        <div>
          <p class="eyebrow">REQUEST FLOW</p>
          <h3>LLM 节流与并发</h3>
        </div>
        <strong>{{ estimatedCalls }}</strong>
      </div>
      <p class="helper">
        当前预计会触发 {{ estimatedCalls }} 次模型请求。并发只会压缩总耗时，不会减少请求总数。
      </p>
    </article>

    <article class="control-card">
      <label for="llmParallelism">同阶段并发数</label>
      <input id="llmParallelism" :value="parallelism" type="number" min="1" @input="updateParallelism" />
      <div class="preset-row">
        <button
          v-for="preset in stagePresets"
          :key="preset"
          type="button"
          class="preset-btn"
          @click="$emit('update:parallelism', preset)"
        >
          x{{ preset }}
        </button>
      </div>
      <span>只控制同一期、同一阶段内的 agent 并发。</span>
    </article>

    <article class="control-card">
      <label for="issueParallelism">验证期并发数</label>
      <input
        id="issueParallelism"
        :value="issueParallelism"
        type="number"
        min="1"
        :disabled="issueParallelismLocked"
        @input="updateIssueParallelism"
      />
      <div class="preset-row">
        <button
          v-for="preset in issuePresets"
          :key="preset"
          type="button"
          class="preset-btn"
          :disabled="issueParallelismLocked"
          @click="$emit('update:issueParallelism', preset)"
        >
          x{{ preset }}
        </button>
      </div>
      <span>
        {{ issueParallelismLocked ? 'world_v1 固定为 1，跨期必须严格因果顺序。' : '并发越高，传统验证越快。' }}
      </span>
    </article>

    <article class="control-card">
      <label for="llmDelayMs">请求间隔</label>
      <input id="llmDelayMs" :value="modelValue" type="number" min="0" max="30000" @input="updateDelay" />
      <div class="preset-row">
        <button
          v-for="preset in delayPresets"
          :key="preset"
          type="button"
          class="preset-btn"
          @click="$emit('update:modelValue', preset)"
        >
          {{ preset }} ms
        </button>
      </div>
      <span>对每次 LLM 请求生效。上游不稳定时，可用它降低瞬时压力。</span>
    </article>

    <article class="control-card">
      <label for="llmRetryCount">瞬时重试次数</label>
      <input id="llmRetryCount" :value="retryCount" type="number" min="0" max="5" @input="updateRetryCount" />
      <div class="preset-row">
        <button
          v-for="preset in retryPresets"
          :key="preset"
          type="button"
          class="preset-btn"
          @click="$emit('update:retryCount', preset)"
        >
          {{ preset }} 次
        </button>
      </div>
      <span>只补偿网络抖动和上游 5xx，不做静默降级。</span>
    </article>

    <article class="control-card">
      <label for="llmRetryBackoffMs">重试退避</label>
      <input
        id="llmRetryBackoffMs"
        :value="retryBackoffMs"
        type="number"
        min="0"
        max="15000"
        @input="updateRetryBackoff"
      />
      <div class="preset-row">
        <button
          v-for="preset in backoffPresets"
          :key="preset"
          type="button"
          class="preset-btn"
          @click="$emit('update:retryBackoffMs', preset)"
        >
          {{ preset }} ms
        </button>
      </div>
      <span>每次重试按 1x、2x、3x 线性退避。</span>
    </article>

    <article class="control-card">
      <label class="switch-row">
        <input
          :checked="dialogueEnabled"
          type="checkbox"
          @change="$emit('update:dialogueEnabled', $event.target.checked)"
        />
        <span>启用 agent 对话</span>
      </label>
      <p class="helper">开启后，主策略组、社交组和裁判组都会多轮讨论。</p>
    </article>

    <article class="control-card">
      <label for="dialogueRounds">对话轮数</label>
      <input
        id="dialogueRounds"
        :value="dialogueRounds"
        type="number"
        min="0"
        max="3"
        @input="updateDialogueRounds"
      />
      <div class="preset-row">
        <button
          v-for="preset in dialoguePresets"
          :key="preset"
          type="button"
          class="preset-btn"
          @click="$emit('update:dialogueRounds', preset)"
        >
          {{ preset }} 轮
        </button>
      </div>
      <span>每增加 1 轮，所有可对话 LLM agent 都会多发 1 次请求。</span>
    </article>
  </div>
</template>

<script setup>
defineProps({
  modelValue: { type: Number, default: 0 },
  estimatedCalls: { type: Number, default: 0 },
  parallelism: { type: Number, default: 1 },
  issueParallelism: { type: Number, default: 1 },
  issueParallelismLocked: { type: Boolean, default: false },
  retryCount: { type: Number, default: 2 },
  retryBackoffMs: { type: Number, default: 1500 },
  dialogueEnabled: { type: Boolean, default: true },
  dialogueRounds: { type: Number, default: 1 }
})

const emit = defineEmits([
  'update:modelValue',
  'update:parallelism',
  'update:issueParallelism',
  'update:retryCount',
  'update:retryBackoffMs',
  'update:dialogueEnabled',
  'update:dialogueRounds'
])

const delayPresets = [0, 1000, 3000, 5000]
const stagePresets = [1, 2, 4, 6, 8, 12, 16]
const issuePresets = [1, 2, 3, 4, 6]
const retryPresets = [0, 1, 2, 3]
const backoffPresets = [500, 1500, 3000, 5000]
const dialoguePresets = [0, 1, 2, 3]

const clamp = (value, min, max) => Math.max(min, Math.min(max, value))

const updateDelay = (event) => {
  const next = clamp(Number(event.target.value || 0), 0, 30000)
  event.target.value = next
  emit('update:modelValue', next)
}

const updateParallelism = (event) => {
  const next = Math.max(1, Number(event.target.value || 1))
  event.target.value = next
  emit('update:parallelism', next)
}

const updateIssueParallelism = (event) => {
  const next = Math.max(1, Number(event.target.value || 1))
  event.target.value = next
  emit('update:issueParallelism', next)
}

const updateRetryCount = (event) => {
  const next = clamp(Number(event.target.value || 0), 0, 5)
  event.target.value = next
  emit('update:retryCount', next)
}

const updateRetryBackoff = (event) => {
  const next = clamp(Number(event.target.value || 0), 0, 15000)
  event.target.value = next
  emit('update:retryBackoffMs', next)
}

const updateDialogueRounds = (event) => {
  const next = clamp(Number(event.target.value || 0), 0, 3)
  event.target.value = next
  emit('update:dialogueRounds', next)
}
</script>

<style scoped>
.control-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.9rem;
}

.control-card {
  display: grid;
  gap: 0.8rem;
  padding: 1rem;
  border-radius: 1.15rem;
  border: 1px solid var(--lottery-line, rgba(31, 28, 24, 0.1));
  background: rgba(255, 255, 255, 0.68);
}

.control-card.accent {
  background: linear-gradient(135deg, rgba(15, 118, 110, 0.12), rgba(255, 255, 255, 0.78));
}

.card-head,
.switch-row {
  display: flex;
  justify-content: space-between;
  gap: 0.8rem;
  align-items: center;
}

.eyebrow,
.helper,
.control-card span {
  margin: 0;
  font-size: 0.8rem;
  line-height: 1.6;
  color: var(--lottery-muted, #6e675f);
}

.control-card label {
  font-weight: 700;
}

.control-card input {
  width: 100%;
  border-radius: 0.9rem;
  border: 1px solid var(--lottery-line-strong, rgba(31, 28, 24, 0.16));
  padding: 0.8rem 0.9rem;
  font: inherit;
  background: rgba(255, 255, 255, 0.88);
}

.switch-row input {
  width: auto;
}

.preset-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.55rem;
}

.preset-btn {
  border: 1px solid var(--lottery-line-strong, rgba(31, 28, 24, 0.16));
  border-radius: 999px;
  padding: 0.4rem 0.75rem;
  background: rgba(255, 255, 255, 0.9);
  cursor: pointer;
  font: inherit;
  font-size: 0.78rem;
}

@media (max-width: 720px) {
  .control-grid {
    grid-template-columns: 1fr;
  }
}
</style>
