<template>
  <section class="panel">
    <div class="panel-header">
      <div>
        <p class="eyebrow">COORDINATION</p>
        <h2>Agent 协作过程</h2>
      </div>
    </div>

    <div v-if="!trace.length" class="empty-state">
      当前还没有可展示的协作轨迹。只有待预测期真正跑完之后，这里才会出现主策略、社交组和裁判组的讨论过程。
    </div>

    <div v-else class="stage-list">
      <article v-for="stage in trace" :key="stage.stage" class="stage-card">
        <div class="stage-top">
          <div>
            <strong>{{ stage.title }}</strong>
            <p>{{ stageDescription(stage.stage) }}</p>
          </div>
          <span>{{ stage.items.length }} 个 agent</span>
        </div>

        <div class="item-list">
          <div v-for="item in stage.items" :key="`${stage.stage}-${item.strategy_id}`" class="item-card">
            <div class="item-head">
              <strong>{{ item.display_name }}</strong>
              <span class="group-tag">{{ groupLabel(item.group) }}</span>
            </div>

            <div v-if="item.numbers?.length" class="number-row">
              <span v-for="num in item.numbers" :key="`${item.strategy_id}-${num}`" class="number-chip">
                {{ num }}
              </span>
            </div>

            <div v-if="item.numbers_before?.length" class="diff-box">
              <span>修正前：{{ item.numbers_before.join(', ') }}</span>
              <span>修正后：{{ item.numbers_after.join(', ') }}</span>
            </div>

            <p v-if="item.rationale">{{ item.rationale }}</p>
            <p v-if="item.comment" class="comment-box">{{ item.comment }}</p>

            <div v-if="item.peer_strategy_ids?.length" class="peer-box">
              <span>读取对象</span>
              <div class="peer-list">
                <span v-for="peer in item.peer_strategy_ids" :key="`${item.strategy_id}-${peer}`" class="peer-tag">
                  {{ peer }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup>
import { groupLabel } from '../utils/lotteryDisplay'

defineProps({
  trace: {
    type: Array,
    default: () => []
  }
})

const stageDescription = (stage) => {
  if (stage === 'primary') return '主策略先独立出号，不读取任何同轮输出。'
  if (stage.startsWith('primary_dialogue_round_')) return '主策略 LLM 互相读结果、评论并修正自己的号码。'
  if (stage === 'social_initial') return '社交组先看主策略战绩和发言，再像真人看榜单一样发帖给出自己的方案。'
  if (stage.startsWith('social_dialogue_round_')) return '社交组内部继续跟帖交流，比较谁更值得信任，再决定是否修正。'
  if (stage === 'judge_initial') return '裁判组读取主策略和社交组候选，形成第一轮裁决。'
  if (stage.startsWith('judge_dialogue_round_')) return '裁判组内部继续对话，交换裁决理由后再次修正。'
  if (stage === 'judge') return '这是裁判组最终对外输出的版本。'
  return ''
}
</script>

<style scoped>
.panel {
  display: grid;
  gap: 1rem;
  padding: 1.35rem;
  border-radius: 1.5rem;
  background: var(--lottery-panel, rgba(255, 251, 244, 0.92));
  border: 1px solid var(--lottery-line, rgba(31, 28, 24, 0.1));
  box-shadow: var(--lottery-shadow, 0 18px 40px rgba(24, 22, 19, 0.08));
}

.panel-header,
.stage-top,
.item-head {
  display: flex;
  justify-content: space-between;
  gap: 0.8rem;
  align-items: flex-start;
}

.eyebrow,
.stage-top p,
.item-card p,
.peer-box span,
.diff-box span {
  margin: 0;
  font-size: 0.82rem;
  line-height: 1.6;
  color: var(--lottery-muted, #6e675f);
}

.empty-state {
  padding: 1.2rem;
  border-radius: 1.2rem;
  border: 1px dashed var(--lottery-line-strong, rgba(31, 28, 24, 0.16));
  color: var(--lottery-muted, #6e675f);
}

.stage-list,
.item-list {
  display: grid;
  gap: 0.85rem;
}

.stage-card,
.item-card {
  display: grid;
  gap: 0.85rem;
  padding: 1rem;
  border-radius: 1.15rem;
  border: 1px solid var(--lottery-line, rgba(31, 28, 24, 0.1));
  background: rgba(255, 255, 255, 0.72);
}

.number-row,
.peer-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.55rem;
}

.number-chip,
.peer-tag,
.group-tag {
  display: inline-flex;
  align-items: center;
  padding: 0.34rem 0.72rem;
  border-radius: 999px;
  font-size: 0.78rem;
}

.number-chip {
  background: var(--lottery-ink, #1d1b19);
  color: #fff;
}

.peer-tag,
.group-tag {
  background: rgba(15, 118, 110, 0.08);
  color: var(--lottery-muted, #6e675f);
}

.comment-box,
.diff-box {
  display: grid;
  gap: 0.45rem;
  padding: 0.85rem;
  border-radius: 0.95rem;
  background: rgba(246, 243, 236, 0.8);
}

.peer-box {
  display: grid;
  gap: 0.45rem;
}
</style>
