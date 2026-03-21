<template>
  <section class="graph-shell">
    <header class="graph-header">
      <div>
        <p class="eyebrow">WORLD GRAPH</p>
        <h2>世界关系图</h2>
      </div>
      <div class="graph-metrics">
        <span>节点 {{ graph?.metrics?.node_count || 0 }}</span>
        <span>连接 {{ graph?.metrics?.edge_count || 0 }}</span>
      </div>
    </header>

    <div class="graph-legend">
      <span><i class="legend-dot agent"></i> Agent</span>
      <span><i class="legend-dot phase"></i> 阶段</span>
    </div>

    <div v-if="!layout.nodes.length" class="empty-state">
      <svg class="empty-icon" viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="32" cy="32" r="28" stroke="currentColor" stroke-width="1.5" stroke-dasharray="4 4" opacity="0.3" />
        <circle cx="32" cy="18" r="4" fill="currentColor" opacity="0.25" />
        <circle cx="18" cy="40" r="3.5" fill="currentColor" opacity="0.2" />
        <circle cx="46" cy="40" r="3.5" fill="currentColor" opacity="0.2" />
        <line x1="32" y1="22" x2="20" y2="37" stroke="currentColor" stroke-width="1" opacity="0.15" />
        <line x1="32" y1="22" x2="44" y2="37" stroke="currentColor" stroke-width="1" opacity="0.15" />
        <line x1="21" y1="40" x2="43" y2="40" stroke="currentColor" stroke-width="1" opacity="0.1" />
      </svg>
      <p class="empty-title">图谱尚未生成</p>
      <p class="empty-hint">推进一轮预测后，世界关系图将在此可视化</p>
    </div>

    <svg v-else class="graph-canvas" :viewBox="`0 0 ${layout.width} ${layout.height}`" role="img">
      <defs>
        <marker id="graph-arrow" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">
          <path d="M0,0 L7,3.5 L0,7 z" fill="rgba(255, 255, 255, 0.45)" />
        </marker>
        <filter id="glow">
          <feGaussianBlur stdDeviation="3" result="coloredBlur"/>
          <feMerge>
            <feMergeNode in="coloredBlur"/>
            <feMergeNode in="SourceGraphic"/>
          </feMerge>
        </filter>
      </defs>

      <line
        v-for="edge in layout.edges"
        :key="edge.id"
        :x1="edge.x1"
        :y1="edge.y1"
        :x2="edge.x2"
        :y2="edge.y2"
        class="graph-edge"
        marker-end="url(#graph-arrow)"
      />

      <g
        v-for="node in layout.nodes"
        :key="node.id"
        class="graph-node"
        :class="[node.node_type, { selected: node.id === selectedNodeId, active: node.active }]"
        @click="$emit('select-node', node.id)"
      >
        <circle :cx="node.x" :cy="node.y" :r="node.radius" class="node-core" />
        <text :x="node.x" :y="node.y + node.radius + 18" class="node-title">{{ node.label }}</text>
        <text :x="node.x" :y="node.y + node.radius + 31" class="node-meta">{{ node.meta }}</text>
      </g>
    </svg>
  </section>
</template>

<script setup>
import { computed } from 'vue'

import { groupLabel, phaseLabel } from '../utils/lotteryDisplay'

const GRAPH_WIDTH = 1040
const GRAPH_HEIGHT = 520
const PHASE_ORDER = [
  'generator_opening',
  'social_propagation',
  'plan_synthesis',
  'final_decision',
  'settlement',
  'postmortem'
]
const GROUP_ORDER = ['data', 'metaphysics', 'hybrid', 'social', 'purchase']

const props = defineProps({
  graph: { type: Object, default: () => ({ nodes: [], edges: [] }) },
  selectedNodeId: { type: String, default: '' }
})

defineEmits(['select-node'])

const layout = computed(() => buildLayout(props.graph || { nodes: [], edges: [] }))

function buildLayout(graph) {
  const nodes = Array.isArray(graph.nodes) ? graph.nodes : []
  const edges = Array.isArray(graph.edges) ? graph.edges : []
  const nodeMap = new Map()
  const positioned = [
    ...placePhaseNodes(nodes, nodeMap),
    ...placeAgentNodes(nodes, nodeMap)
  ]
  return {
    width: GRAPH_WIDTH,
    height: GRAPH_HEIGHT,
    nodes: positioned,
    edges: placeEdges(edges, nodeMap)
  }
}

function placePhaseNodes(nodes, nodeMap) {
  const phaseNodes = nodes
    .filter((item) => item.node_type === 'phase')
    .sort((left, right) => PHASE_ORDER.indexOf(left.phase) - PHASE_ORDER.indexOf(right.phase))
  const coords = evenly(phaseNodes, 100, GRAPH_WIDTH - 100)
  return phaseNodes.map((item, index) => registerNode(nodeMap, {
    ...item,
    x: coords[index],
    y: 96,
    radius: 22,
    meta: phaseLabel(item.phase)
  }))
}

function placeAgentNodes(nodes, nodeMap) {
  const groups = groupedAgents(nodes)
  return GROUP_ORDER.flatMap((group, column) => {
    const items = groups[group] || []
    if (!items.length) return []
    const x = 100 + column * 140
    return items.map((item, row) => registerNode(nodeMap, {
      ...item,
      x,
      y: 230 + row * 74,
      radius: 16,
      meta: `${groupLabel(group)} / ${item.role_kind}`
    }))
  })
}

function groupedAgents(nodes) {
  return nodes
    .filter((item) => item.node_type === 'agent')
    .sort((left, right) => {
      const groupDelta = GROUP_ORDER.indexOf(left.group || 'data') - GROUP_ORDER.indexOf(right.group || 'data')
      return groupDelta || left.label.localeCompare(right.label)
    })
    .reduce((acc, item) => {
      const group = item.group || 'data'
      if (!acc[group]) acc[group] = []
      acc[group].push(item)
      return acc
    }, {})
}

function placeEdges(edges, nodeMap) {
  return edges
    .map((edge) => {
      const source = nodeMap.get(edge.source)
      const target = nodeMap.get(edge.target)
      if (!source || !target) return null
      const angle = Math.atan2(target.y - source.y, target.x - source.x)
      return {
        ...edge,
        x1: source.x + Math.cos(angle) * source.radius,
        y1: source.y + Math.sin(angle) * source.radius,
        x2: target.x - Math.cos(angle) * target.radius,
        y2: target.y - Math.sin(angle) * target.radius
      }
    })
    .filter(Boolean)
}

function registerNode(nodeMap, item) {
  nodeMap.set(item.id, item)
  return item
}

function evenly(items, start, end) {
  if (!items.length) return []
  if (items.length === 1) return [Math.round((start + end) / 2)]
  const step = (end - start) / (items.length - 1)
  return items.map((_, index) => Math.round(start + step * index))
}
</script>

<style scoped>
.graph-shell {
  display: grid;
  gap: 0.9rem;
  padding: 1.15rem;
  border-radius: 1.5rem;
  border: 1px solid var(--lottery-line, rgba(88, 66, 39, 0.12));
  background: linear-gradient(180deg, rgba(255, 253, 249, 0.86), rgba(247, 241, 232, 0.92));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.5);
  color: var(--lottery-panel-ink, #2f251a);
}

.graph-header,
.graph-metrics,
.graph-legend {
  display: flex;
  gap: 0.75rem;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
}

.graph-legend {
  justify-content: flex-start;
  color: var(--lottery-muted, #6d5a48);
  font-size: 0.84rem;
}

.legend-dot {
  display: inline-block;
  width: 0.65rem;
  height: 0.65rem;
  border-radius: 999px;
  margin-right: 0.3rem;
}

.legend-dot.agent {
  background: var(--lottery-teal, #2f776b);
  box-shadow: 0 0 0 4px rgba(47, 119, 107, 0.12);
}

.legend-dot.phase {
  background: var(--lottery-accent, #a66a2c);
  box-shadow: 0 0 0 4px rgba(166, 106, 44, 0.12);
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 3rem 1rem;
  text-align: center;
}

.empty-icon {
  width: 5rem;
  height: 5rem;
  color: var(--lottery-teal, #2f776b);
  margin-bottom: 1.25rem;
  animation: subtleBreathe 3s ease-in-out infinite;
}

@keyframes subtleBreathe {
  0%, 100% { opacity: 0.45; transform: scale(1); }
  50% { opacity: 0.8; transform: scale(1.05); }
}

.empty-title {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 600;
  color: var(--lottery-panel-ink, #2f251a);
}

.empty-hint {
  margin: 0.35rem 0 0;
  color: var(--lottery-muted, #6d5a48);
  font-size: 0.85rem;
}

.graph-canvas {
  width: 100%;
  min-height: 28rem;
}

.graph-edge {
  stroke: rgba(109, 90, 72, 0.22);
  stroke-width: 1.5;
}

.graph-node {
  cursor: pointer;
  transition: opacity 0.2s;
}

.node-core {
  fill: rgba(47, 119, 107, 0.12);
  stroke: rgba(47, 119, 107, 0.32);
  stroke-width: 2;
  transition: all 0.25s ease;
}

.graph-node:hover .node-core {
  fill: rgba(47, 119, 107, 0.18);
  stroke: rgba(47, 119, 107, 0.48);
}

.graph-node.phase .node-core {
  fill: rgba(166, 106, 44, 0.14);
  stroke: rgba(166, 106, 44, 0.36);
}

.graph-node.phase:hover .node-core {
  fill: rgba(166, 106, 44, 0.22);
  stroke: rgba(166, 106, 44, 0.56);
}

.graph-node.selected .node-core,
.graph-node.active .node-core {
  stroke: var(--lottery-panel-ink, #2f251a);
  stroke-width: 2.5;
  filter: url(#glow);
}

.node-title,
.node-meta,
.eyebrow,
.graph-header h2 {
  margin: 0;
  text-anchor: middle;
}

.node-title {
  fill: var(--lottery-panel-ink, #2f251a);
  font-size: 0.82rem;
  font-weight: 600;
}

.node-meta {
  fill: var(--lottery-muted, #6d5a48);
  font-size: 0.7rem;
}

.eyebrow {
  color: var(--lottery-accent-strong, #7e4b1d);
}

.graph-header h2 {
  color: var(--lottery-panel-ink, #2f251a);
  font-size: 1.3rem;
}

.graph-metrics span {
  font-size: 0.82rem;
  color: var(--lottery-muted, #6d5a48);
}
</style>
