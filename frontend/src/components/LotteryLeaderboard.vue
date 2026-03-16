<template>
  <section class="panel">
    <div class="panel-header">
      <div>
        <p class="eyebrow">LEADERBOARD</p>
        <h2>Agent 排行</h2>
      </div>
      <span class="count-pill">{{ leaderboard.length }} 个策略</span>
    </div>

    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Agent</th>
            <th>组别</th>
            <th>类型</th>
            <th>均命中</th>
            <th>波动</th>
            <th>近 5 期</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(row, index) in leaderboard"
            :key="row.strategy_id"
            :class="{ active: row.strategy_id === selectedId }"
            @click="$emit('select', row.strategy_id)"
          >
            <td>{{ index + 1 }}</td>
            <td>
              <strong>{{ row.display_name }}</strong>
              <p>{{ row.strategy_id }}</p>
            </td>
            <td><span class="group-tag">{{ groupLabel(row.group) }}</span></td>
            <td><span class="kind-tag" :class="row.kind">{{ kindLabel(row.kind) }}</span></td>
            <td>{{ row.average_hits }}</td>
            <td>{{ row.hit_stddev }}</td>
            <td>
              <div class="hit-strip">
                <span
                  v-for="item in row.issue_hits.slice(-5)"
                  :key="`${row.strategy_id}-${item.period}`"
                  :class="['hit-pill', `hit-${item.hits}`]"
                >
                  {{ item.hits }}
                </span>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<script setup>
import { groupLabel, kindLabel } from '../utils/lotteryDisplay'

defineProps({
  leaderboard: {
    type: Array,
    default: () => []
  },
  selectedId: {
    type: String,
    default: ''
  }
})

defineEmits(['select'])
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

.panel-header {
  display: flex;
  justify-content: space-between;
  gap: 0.8rem;
  align-items: center;
}

.eyebrow {
  margin: 0;
  font-size: 0.82rem;
  color: var(--lottery-muted, #6e675f);
}

.count-pill,
.group-tag,
.kind-tag,
.hit-pill {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
}

.count-pill {
  padding: 0.35rem 0.8rem;
  background: rgba(255, 255, 255, 0.72);
  color: var(--lottery-muted, #6e675f);
}

.table-wrap {
  overflow: auto;
}

table {
  width: 100%;
  min-width: 48rem;
  border-collapse: separate;
  border-spacing: 0;
}

th,
td {
  padding: 0.95rem 0.75rem;
  text-align: left;
  border-bottom: 1px solid var(--lottery-line, rgba(31, 28, 24, 0.1));
  vertical-align: middle;
}

thead th {
  position: sticky;
  top: 0;
  z-index: 1;
  background: rgba(250, 247, 239, 0.96);
  backdrop-filter: blur(10px);
}

tbody tr {
  cursor: pointer;
  transition: background 0.2s ease, transform 0.2s ease;
}

tbody tr:hover,
tbody tr.active {
  background: rgba(15, 118, 110, 0.06);
}

td p {
  margin: 0.3rem 0 0;
  font-size: 0.78rem;
  color: var(--lottery-muted, #6e675f);
}

.kind-tag,
.group-tag {
  padding: 0.3rem 0.65rem;
  font-size: 0.76rem;
  border: 1px solid var(--lottery-line-strong, rgba(31, 28, 24, 0.16));
}

.kind-tag.llm {
  background: var(--lottery-ink, #1d1b19);
  color: #fff;
}

.group-tag {
  color: var(--lottery-muted, #6e675f);
  background: rgba(255, 255, 255, 0.72);
}

.hit-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
}

.hit-pill {
  min-width: 1.9rem;
  justify-content: center;
  padding: 0.28rem 0.45rem;
  font-size: 0.76rem;
  border: 1px solid var(--lottery-line-strong, rgba(31, 28, 24, 0.16));
}

.hit-0 {
  opacity: 0.42;
}

.hit-1,
.hit-2 {
  background: rgba(255, 255, 255, 0.78);
}

.hit-3,
.hit-4,
.hit-5,
.hit-6,
.hit-7,
.hit-8,
.hit-9,
.hit-10 {
  background: var(--lottery-ink, #1d1b19);
  color: #fff;
}
</style>
