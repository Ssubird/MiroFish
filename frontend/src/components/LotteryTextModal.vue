<template>
  <Teleport to="body">
    <div v-if="visible" class="modal-overlay" @click.self="close">
      <div class="modal-container">
        <header class="modal-header">
          <h2>{{ title }}</h2>
          <button class="close-btn" @click="close">&times;</button>
        </header>
        <div class="modal-body">
          <pre v-if="format === 'code'">{{ content }}</pre>
          <div v-else-if="format === 'markdown'" class="markdown-body">{{ content }}</div>
          <p v-else class="text-body" style="white-space: pre-wrap">{{ content }}</p>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
defineProps({
  visible: { type: Boolean, default: false },
  title: { type: String, default: '详情' },
  content: { type: String, default: '' },
  format: { type: String, default: 'text' }
})

const emit = defineEmits(['update:visible'])

const close = () => {
  emit('update:visible', false)
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 10000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(42, 31, 19, 0.36);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  animation: fadeIn 0.2s ease-out;
}

.modal-container {
  width: 90%;
  max-width: 800px;
  max-height: 85vh;
  display: flex;
  flex-direction: column;
  background: linear-gradient(180deg, rgba(255, 252, 248, 0.98), rgba(247, 240, 229, 0.96));
  border: 1px solid var(--lottery-line, rgba(88, 66, 39, 0.12));
  border-radius: 1.25rem;
  box-shadow: 0 28px 56px rgba(77, 57, 33, 0.2);
  color: var(--lottery-panel-ink, #2f251a);
  overflow: hidden;
  animation: slideUp 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1.25rem 1.5rem;
  border-bottom: 1px solid var(--lottery-line, rgba(88, 66, 39, 0.12));
  background: rgba(255, 255, 255, 0.46);
}

.modal-header h2 {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--lottery-panel-ink, #2f251a);
}

.close-btn {
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid var(--lottery-line, rgba(88, 66, 39, 0.12));
  color: var(--lottery-muted, #6d5a48);
  font-size: 1.75rem;
  line-height: 1;
  cursor: pointer;
  padding: 0 0.55rem;
  border-radius: 0.75rem;
  transition: all 0.2s;
}

.close-btn:hover {
  color: var(--lottery-panel-ink, #2f251a);
  background: rgba(255, 255, 255, 0.96);
}

.modal-body {
  padding: 1.5rem;
  overflow-y: auto;
  font-size: 1rem;
  line-height: 1.7;
}

.text-body {
  margin: 0;
  color: var(--lottery-panel-ink, #2f251a);
}

.modal-body pre {
  margin: 0;
  background: rgba(255, 255, 255, 0.72);
  padding: 1.25rem;
  border-radius: 0.9rem;
  border: 1px solid var(--lottery-line, rgba(88, 66, 39, 0.12));
  overflow-x: auto;
  font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 0.88rem;
  color: var(--lottery-muted, #6d5a48);
  white-space: pre-wrap;
  word-break: break-word;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes slideUp {
  from { opacity: 0; transform: translateY(20px) scale(0.98); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}
</style>
