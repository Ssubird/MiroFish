<template>
  <section class="panel">
    <div class="panel-header">
      <div>
        <p class="eyebrow">INSPECTOR</p>
        <h2>策略过程拆解</h2>
      </div>
    </div>

    <div v-if="!strategy" class="empty-state">
      从左侧选择一个 agent，这里会展示它的待预测输出、提示词、对话修正和最近 10 期回测表现。
    </div>

    <template v-else>
      <article class="hero-card">
        <div class="hero-top">
          <div>
            <h3>{{ strategy.display_name }}</h3>
            <p>{{ strategy.description }}</p>
          </div>
          <div class="tag-row">
            <span class="group-tag">{{ groupLabel(strategy.group) }}</span>
            <span class="kind-tag" :class="strategy.kind">{{ kindLabel(strategy.kind) }}</span>
          </div>
        </div>

        <div class="stat-grid">
          <div v-for="item in metricCards" :key="item.label">
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
          </div>
        </div>

        <div v-if="strategy.uses_llm" class="note-card">
          这是一个真实调用模型的 agent。每个回测期都会单独请求模型，不是本地模拟。
        </div>
        <div v-if="strategy.group === 'judge'" class="note-card subtle">
          裁判组会先读取主策略和社交组候选，再和其他裁判继续对话，最后给出裁决版本。
        </div>
        <div v-if="strategy.group === 'social'" class="note-card subtle">
          社交组会先看排行榜和主策略发言，再像真人看报告一样发帖讨论，并把信任对象写进元数据。
        </div>
      </article>

      <article v-if="latestPrediction" class="detail-card">
        <div class="section-head">
          <strong>最新待预测期输出</strong>
          <span>{{ latestPrediction.strategy_id }}</span>
        </div>
        <p class="rationale">
          {{ shortText(latestPrediction.rationale, 180) }}
          <button v-if="(latestPrediction.rationale || '').length > 180" class="text-link" @click="$emit('view-details', {title: '预测理由', content: latestPrediction.rationale})">阅读全文</button>
        </p>
        <div class="chips">
          <span v-for="num in latestPrediction.numbers" :key="`${latestPrediction.strategy_id}-${num}`" class="chip">
            {{ num }}
          </span>
        </div>

        <div v-for="block in metaBlocks" :key="block.label" class="meta-block">
          <template v-if="block.items.length">
            <span>{{ block.label }}</span>
            <div class="chips">
              <span v-for="item in block.items" :key="`${block.label}-${item}`" class="chip alt">{{ item }}</span>
            </div>
          </template>
        </div>

        <div v-if="dialogueHistory.length" class="meta-block">
          <span>对话修正</span>
          <div class="dialogue-list">
            <div v-for="item in dialogueHistory" :key="`${latestPrediction.strategy_id}-${item.round}`" class="dialogue-item">
              <strong>第 {{ item.round }} 轮</strong>
              <p>{{ item.comment || '无评论' }}</p>
              <span>{{ item.numbers_before.join(', ') }} -> {{ item.numbers_after.join(', ') }}</span>
            </div>
          </div>
        </div>

        <div v-for="block in promptBlocks" :key="block.label" class="prompt-block">
          <template v-if="block.value">
            <div class="prompt-header">
              <span>{{ block.label }}</span>
              <button class="ghost-btn small font-inherit" @click="$emit('view-details', {title: block.label, content: block.value, format: 'code'})">查看完整</button>
            </div>
          </template>
        </div>
      </article>

      <div class="issue-list">
        <article v-for="item in recentIssues" :key="`${strategy.strategy_id}-${item.period}`" class="issue-card">
          <div class="issue-top">
            <strong>{{ item.period }}</strong>
            <span :class="['hit-badge', `hit-${item.hits}`]">{{ item.hits }} hit</span>
          </div>
          <p class="issue-date">{{ item.date }}</p>
          <div class="numbers-block">
            <span>预测号码</span>
            <div class="chips">
              <span v-for="num in item.predicted_numbers" :key="`p-${item.period}-${num}`" class="chip">{{ num }}</span>
            </div>
          </div>
          <div class="numbers-block">
            <span>实际号码</span>
            <div class="chips">
              <span v-for="num in item.actual_numbers" :key="`a-${item.period}-${num}`" class="chip solid">{{ num }}</span>
            </div>
          </div>
        </article>
      </div>
    </template>
  </section>
</template>

<script setup>
import { computed } from 'vue'

import { groupLabel, kindLabel, shortText } from '../utils/lotteryDisplay'

const props = defineProps({
  strategy: {
    type: Object,
    default: null
  }
})

defineEmits(['view-details'])

const safeList = (value) => (Array.isArray(value) ? value : [])

const latestPrediction = computed(() => props.strategy?.latest_prediction || null)
const recentIssues = computed(() => props.strategy?.issue_hits?.slice(-10).reverse() || [])
const metricCards = computed(() => [
  { label: '均命中', value: props.strategy?.average_hits ?? '-' },
  { label: '总命中', value: props.strategy?.total_hits ?? '-' },
  { label: '波动', value: props.strategy?.hit_stddev ?? '-' },
  { label: '历史需求', value: props.strategy?.required_history ?? '-' }
])
const sourceList = computed(() => safeList(latestPrediction.value?.metadata?.sources))
const peerList = computed(() => safeList(latestPrediction.value?.metadata?.peer_strategy_ids))
const judgePeerList = computed(() => safeList(latestPrediction.value?.metadata?.judge_peer_strategy_ids))
const socialPeerList = computed(() => safeList(latestPrediction.value?.metadata?.social_peer_strategy_ids))
const trustedList = computed(() => safeList(latestPrediction.value?.metadata?.trusted_strategy_ids))
const dialogueHistory = computed(() => safeList(latestPrediction.value?.metadata?.dialogue_history))
const metaBlocks = computed(() => [
  { label: '知识来源', items: sourceList.value },
  { label: '读取对象', items: peerList.value },
  { label: '裁判对话对象', items: judgePeerList.value },
  { label: '社交对话对象', items: socialPeerList.value },
  { label: '信任策略', items: trustedList.value }
])
const promptBlocks = computed(() => [
  { label: 'System Prompt', value: latestPrediction.value?.metadata?.system_prompt || '' },
  { label: 'User Prompt Preview', value: latestPrediction.value?.metadata?.user_prompt_preview || '' },
  { label: 'Dialogue Prompt', value: latestPrediction.value?.metadata?.dialogue_system_prompt || '' },
  { label: 'Dialogue User Prompt Preview', value: latestPrediction.value?.metadata?.dialogue_user_prompt_preview || '' }
])
</script>

<style scoped>
.panel { display: grid; gap: 1rem; padding: 1.35rem; border-radius: 1.5rem; background: var(--lottery-panel, rgba(255, 251, 244, 0.92)); border: 1px solid var(--lottery-line, rgba(31, 28, 24, 0.1)); box-shadow: var(--lottery-shadow, 0 18px 40px rgba(24, 22, 19, 0.08)); }
.panel-header, .hero-top, .section-head, .issue-top { display: flex; justify-content: space-between; gap: 0.8rem; align-items: flex-start; }
.eyebrow, .empty-state, .hero-card p, .note-card, .meta-block span, .dialogue-item p, .issue-date, .numbers-block span, .rationale { margin: 0; font-size: 0.82rem; line-height: 1.6; color: var(--lottery-muted, #6e675f); }
.empty-state { padding: 1.2rem; border-radius: 1.2rem; border: 1px dashed var(--lottery-line-strong, rgba(31, 28, 24, 0.16)); }
.hero-card, .detail-card, .issue-card { display: grid; gap: 0.95rem; padding: 1rem; border-radius: 1.15rem; border: 1px solid var(--lottery-line, rgba(31, 28, 24, 0.1)); background: rgba(255, 255, 255, 0.72); }
.tag-row, .chips { display: flex; flex-wrap: wrap; gap: 0.55rem; }
.kind-tag, .group-tag, .chip, .hit-badge { display: inline-flex; align-items: center; padding: 0.32rem 0.7rem; border-radius: 999px; font-size: 0.76rem; }
.kind-tag.llm, .chip.solid { background: var(--lottery-ink, #1d1b19); color: #fff; }
.group-tag, .chip.alt, .chip { background: rgba(255, 255, 255, 0.75); border: 1px solid var(--lottery-line-strong, rgba(31, 28, 24, 0.16)); }
.stat-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 0.75rem; }
.stat-grid div, .dialogue-item { display: grid; gap: 0.35rem; padding: 0.9rem; border-radius: 1rem; background: rgba(246, 243, 236, 0.8); }
.note-card { padding: 0.85rem 1rem; border-radius: 1rem; background: rgba(15, 118, 110, 0.08); }
.note-card.subtle { background: rgba(183, 121, 31, 0.08); }
.meta-block, .prompt-block, .dialogue-list, .issue-list, .numbers-block { display: grid; gap: 0.65rem; }
.prompt-header { display: flex; justify-content: space-between; align-items: center; border: 1px dashed rgba(31, 28, 24, 0.2); padding: 0.6rem 0.8rem; border-radius: 0.75rem; background: rgba(255, 255, 255, 0.75); }
.prompt-header span { font-size: 0.85rem; font-weight: 500; color: #433; }
.ghost-btn.small { padding: 0.3rem 0.8rem; font-size: 0.8rem; border-radius: 999px; cursor: pointer; border: 1px solid rgba(31, 28, 24, 0.2); background: transparent; }
.ghost-btn.small:hover { background: rgba(31, 28, 24, 0.05); }
.hit-badge { border: 1px solid var(--lottery-line-strong, rgba(31, 28, 24, 0.16)); }
.hit-0 { opacity: 0.42; }
.hit-1, .hit-2 { background: rgba(255, 255, 255, 0.8); }
.hit-3, .hit-4, .hit-5, .hit-6, .hit-7, .hit-8, .hit-9, .hit-10 { background: var(--lottery-ink, #1d1b19); color: #fff; }

.text-link {
  background: none;
  border: none;
  padding: 0;
  margin-left: 0.5rem;
  color: #1a73e8;
  font: inherit;
  font-size: 0.85rem;
  cursor: pointer;
  text-decoration: underline;
  text-decoration-color: rgba(26, 115, 232, 0.4);
  text-underline-offset: 3px;
  transition: all 0.2s ease;
}

.text-link:hover {
  text-decoration-color: #1a73e8;
}

@media (max-width: 900px) { .stat-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 640px) { .stat-grid { grid-template-columns: 1fr; } }
</style>
