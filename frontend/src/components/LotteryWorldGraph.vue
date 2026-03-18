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
      当前还没有可视化节点，先推进一轮预测。
    </div>

    <svg v-else class="graph-canvas" :viewBox="`0 0 ${layout.width} ${layout.height}`" role="img">
      <defs>
        <marker id="graph-arrow" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">
          <path d="M0,0 L7,3.5 L0,7 z" fill="rgba(255, 255, 255, 0.45)" />
        </marker>
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
  'market_rerank',
  'plan_synthesis',
  'handbook_final_decision',
  'settlement',
  'postmortem'
]
const GROUP_ORDER = ['data', 'metaphysics', 'hybrid', 'social', 'judge', 'purchase', 'decision']

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
  gap: 1rem;
  padding: 1.25rem;
  border-radius: 1.5rem;
  border: 1px solid rgba(0, 240, 255, 0.15);
  background: rgba(11, 12, 16, 0.6);
  color: #e0e6ed;
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
  color: #8b9bb4;
}

.legend-dot {
  display: inline-block;
  width: 0.75rem;
  height: 0.75rem;
  border-radius: 999px;
  margin-right: 0.35rem;
}

.legend-dot.agent {
  background: #5dd0ff;
}

.legend-dot.phase {
  background: #ffc14d;
}

.empty-state {
  padding: 1rem;
  border-radius: 1rem;
  background: rgba(255, 255, 255, 0.04);
  color: #8b9bb4;
}

.graph-canvas {
  width: 100%;
  min-height: 32rem;
}

.graph-edge {
  stroke: rgba(255, 255, 255, 0.18);
  stroke-width: 1.5;
}

.graph-node {
  cursor: pointer;
}

.node-core {
  fill: rgba(0, 240, 255, 0.18);
  stroke: rgba(0, 240, 255, 0.35);
  stroke-width: 2;
}

.graph-node.phase .node-core {
  fill: rgba(255, 193, 77, 0.18);
  stroke: rgba(255, 193, 77, 0.45);
}

.graph-node.selected .node-core,
.graph-node.active .node-core {
  stroke: #ffffff;
  stroke-width: 2.5;
}

.node-title,
.node-meta,
.eyebrow,
.graph-header h2 {
  margin: 0;
  text-anchor: middle;
}

.node-title {
  fill: #fff;
  font-size: 0.85rem;
}

.node-meta {
  fill: #8b9bb4;
  font-size: 0.72rem;
}

.eyebrow {
  color: #8b9bb4;
}

.graph-header h2 {
  color: #fff;
  font-size: 1.4rem;
}
</style>
