<template>
  <article class="binding-shell">
    <div class="field-head">
      <div>
        <strong>Session 级执行绑定</strong>
        <p class="muted">这里的改动只影响当前 world session，不会回写 `execution_config.yaml`。</p>
      </div>
      <button type="button" class="ghost-btn" @click="$emit('reset')">恢复默认</button>
    </div>

    <div v-if="providers.length" class="provider-grid">
      <article v-for="provider in providers" :key="provider.provider_id" class="provider-card">
        <strong>{{ provider.provider_id }}</strong>
        <p class="muted">{{ provider.kind || 'openai_compatible' }}</p>
        <p class="muted">{{ provider.base_url || '使用环境变量默认地址' }}</p>
      </article>
    </div>

    <div class="binding-grid">
      <label v-for="group in groupOptions" :key="group.id" class="field">
        <span>{{ group.label }}</span>
        <select :value="group.profileId" @change="emitBinding('group', group.id, $event.target.value)">
          <option value="">配置默认</option>
          <option v-for="profile in profiles" :key="profile.profile_id" :value="profile.profile_id">
            {{ profileLabel(profile) }}
          </option>
        </select>
      </label>
    </div>

    <div v-if="agentRows.length" class="agent-list">
      <div v-for="agent in agentRows" :key="agent.session_agent_id" class="agent-row">
        <div class="agent-copy">
          <strong>{{ agent.display_name }}</strong>
          <p class="muted">{{ agent.group }} / {{ agent.role_kind }}</p>
          <p class="muted">当前：{{ bindingSummary(agent.session_agent_id) }}</p>
        </div>
        <select :value="agentOverride(agent.session_agent_id)" @change="emitBinding('agent', agent.session_agent_id, $event.target.value)">
          <option value="">配置默认</option>
          <option v-for="profile in profiles" :key="`${agent.session_agent_id}-${profile.profile_id}`" :value="profile.profile_id">
            {{ profileLabel(profile) }}
          </option>
        </select>
      </div>
    </div>
  </article>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  catalog: { type: Object, default: null },
  overrides: { type: Object, default: () => ({ group_overrides: {}, agent_overrides: {} }) },
  bindings: { type: Object, default: () => ({}) },
  agents: { type: Array, default: () => [] }
})

const emit = defineEmits(['update-binding', 'reset'])

const GROUPS = [
  ['data', '数据组'],
  ['metaphysics', '玄学组'],
  ['hybrid', '混合组'],
  ['social', '社交层'],
  ['judge', '裁判层'],
  ['purchase', '购买层'],
  ['decision', '终判层']
]

const providers = computed(() => props.catalog?.providers || [])
const profiles = computed(() => props.catalog?.profiles || [])
const agentRows = computed(() => props.agents || [])
const groupOptions = computed(() => GROUPS.map(([id, label]) => ({
  id,
  label,
  profileId: props.overrides?.group_overrides?.[id] || ''
})))

const emitBinding = (scope, key, profileId) => {
  emit('update-binding', { scope, key, profileId: String(profileId || '').trim() })
}

const agentOverride = (agentId) => props.overrides?.agent_overrides?.[agentId] || ''

const bindingSummary = (agentId) => {
  const binding = props.bindings?.[agentId]
  if (!binding) return '-'
  return `${binding.profile_id || '-'} / ${binding.provider_id || '-'} / ${binding.model_id || '-'}`
}

const profileLabel = (profile) => {
  const provider = profile.provider_id || '-'
  const model = profile.model_id || '-'
  return `${profile.profile_id} · ${provider} / ${model}`
}
</script>

<style scoped>
.binding-shell,
.provider-grid,
.binding-grid,
.agent-list {
  display: grid;
  gap: 0.85rem;
}

.field-head,
.agent-row {
  display: flex;
  gap: 0.8rem;
  justify-content: space-between;
  align-items: flex-start;
  flex-wrap: wrap;
}

.provider-grid,
.binding-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.provider-card,
.agent-row {
  padding: 0.95rem 1rem;
  border-radius: 1rem;
  border: 1px solid var(--lottery-line, rgba(31, 28, 24, 0.1));
  background: rgba(255, 255, 255, 0.72);
}

.field,
.agent-copy {
  display: grid;
  gap: 0.4rem;
  min-width: 0;
}

.field span,
.muted,
.provider-card p,
.agent-copy p {
  margin: 0;
  color: var(--lottery-muted, #6e675f);
  overflow-wrap: anywhere;
}

select,
.ghost-btn {
  font: inherit;
}

select {
  width: 100%;
  min-width: 0;
  border-radius: 0.9rem;
  border: 1px solid var(--lottery-line-strong, rgba(31, 28, 24, 0.16));
  padding: 0.85rem 0.95rem;
  background: rgba(255, 255, 255, 0.9);
}

.ghost-btn {
  border-radius: 999px;
  padding: 0.6rem 0.9rem;
  border: 1px solid var(--lottery-line-strong, rgba(31, 28, 24, 0.16));
  background: rgba(255, 255, 255, 0.84);
  cursor: pointer;
}

@media (max-width: 860px) {
  .provider-grid,
  .binding-grid {
    grid-template-columns: 1fr;
  }
}
</style>
