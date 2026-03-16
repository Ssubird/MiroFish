<template>
  <article v-if="reportArtifacts" class="panel">
    <div class="panel-header">
      <div>
        <p class="eyebrow">REPORT</p>
        <h3>本轮报告已保存</h3>
      </div>
      <span class="pill">{{ reportArtifacts.run_id }}</span>
    </div>
    <div class="meta-grid">
      <div class="meta-card">
        <span>保存时间</span>
        <strong>{{ reportArtifacts.saved_at }}</strong>
      </div>
      <div class="meta-card">
        <span>JSON</span>
        <strong>{{ reportArtifacts.json_path }}</strong>
      </div>
      <div class="meta-card">
        <span>Markdown</span>
        <strong>{{ reportArtifacts.markdown_path }}</strong>
      </div>
    </div>
  </article>
</template>

<script setup>
defineProps({
  reportArtifacts: {
    type: Object,
    default: null
  }
})
</script>

<style scoped>
.panel {
  display: grid;
  gap: 0.9rem;
  padding: 1.15rem;
  border-radius: 1.3rem;
  background: rgba(255, 251, 244, 0.94);
  border: 1px solid rgba(31, 28, 24, 0.1);
}

.panel-header {
  display: flex;
  justify-content: space-between;
  gap: 0.8rem;
}

.eyebrow,
.meta-card span {
  margin: 0;
  font-size: 0.78rem;
  color: var(--lottery-muted, #6e675f);
}

.pill {
  display: inline-flex;
  align-items: center;
  padding: 0.32rem 0.7rem;
  border-radius: 999px;
  font-size: 0.76rem;
  background: rgba(255, 255, 255, 0.78);
  border: 1px solid rgba(31, 28, 24, 0.14);
}

.meta-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));
  gap: 0.75rem;
}

.meta-card {
  display: grid;
  gap: 0.35rem;
  padding: 0.85rem;
  border-radius: 1rem;
  background: rgba(255, 255, 255, 0.7);
}

.meta-card strong {
  word-break: break-all;
  line-height: 1.5;
}
</style>
