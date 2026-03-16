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
      <span><i class="legend-dot round"></i> 讨论轮</span>
    </div>

    <div v-if="!layout.nodes.length" class="empty-state">
      当前还没有可视化节点，先点击“同步并推进”。
    </div>

    <svg v-else class="graph-canvas" :viewBox="`0 0 ${layout.width} ${layout.height}`" role="img">
      <defs>
        <marker id="graph-arrow" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto">
          <path d="M0,0 L7,3.5 L0,7 z" fill="rgba(29, 27, 25, 0.35)" />
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
        :class="`edge-${edge.relation}`"
        marker-end="url(#graph-arrow)"
      />

      <g
        v-for="node in layout.nodes"
        :key="node.id"
        class="graph-node"
        :class="[node.node_type, { selected: node.id === selectedNodeId, active: node.active }]"
        @click="$emit('select-node', node.id)"
      >
        <circle :cx="node.x" :cy="node.y" :r="node.radius" />
        <text :x="node.x" :y="node.y + node.radius + 15" class="node-title">{{ node.label }}</text>
        <text :x="node.x" :y="node.y + node.radius + 28" class="node-meta">{{ node.meta }}</text>
      </g>
    </svg>
  </section>
</template>

<script setup>
import { computed } from 'vue'

import { groupLabel, phaseLabel } from '../utils/lotteryDisplay'

const GRAPH_WIDTH = 1040
const GRAPH_HEIGHT = 500
const PHASE_ORDER = ['opening', 'public_debate', 'judge_synthesis', 'purchase_committee', 'settlement', 'postmortem']
const GROUP_ORDER = ['data', 'metaphysics', 'hybrid', 'analyst', 'purchase']

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
    ...placeDebateNodes(nodes, nodeMap),
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
  const coords = evenly(phaseNodes, 120, GRAPH_WIDTH - 120)
  return phaseNodes.map((item, index) => {
    const x = coords[index]
    return registerNode(nodeMap, {
      ...item,
      x,
      y: 92,
      radius: 19,
      meta: phaseLabel(item.phase)
    })
  })
}

function placeDebateNodes(nodes, nodeMap) {
  const debateNodes = nodes
    .filter((item) => item.node_type === 'debate_round')
    .sort((left, right) => left.label.localeCompare(right.label))
  const coords = evenly(debateNodes, GRAPH_WIDTH * 0.36, GRAPH_WIDTH * 0.64)
  return debateNodes.map((item, index) => {
    const x = coords[index]
    return registerNode(nodeMap, {
      ...item,
      x,
      y: 188,
      radius: 14,
      meta: item.summary || `第 ${index + 1} 轮`
    })
  })
}

function placeAgentNodes(nodes, nodeMap) {
  const groups = groupedAgents(nodes)
  return GROUP_ORDER.flatMap((group) => {
    const items = groups[group] || []
    if (!items.length) return []
    const column = GROUP_ORDER.indexOf(group)
    const x = 120 + column * 200
    return items.map((item, row) => registerNode(nodeMap, {
      ...item,
      x,
      y: 294 + row * 66,
      radius: 12,
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

function evenly(items, start, end) {
  if (!items.length) return []
  if (items.length === 1) return [Math.round((start + end) / 2)]
  const step = (end - start) / (items.length - 1)
  return items.map((_, index) => Math.round(start + step * index))
}

function registerNode(nodeMap, node) {
  nodeMap.set(node.id, node)
  return node
}
</script>

<style scoped>
.graph-shell {
  display: grid;
  gap: 0.85rem;
  padding: 1.1rem 1.15rem 1.2rem;
  border-radius: 1.5rem;
  border: 1px solid rgba(31, 28, 24, 0.1);
  background: rgba(255, 251, 244, 0.92);
  box-shadow: 0 18px 42px rgba(29, 27, 25, 0.08);
}

.graph-header,
.graph-metrics,
.graph-legend {
  display: flex;
  gap: 0.8rem;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
}

.graph-metrics,
.graph-legend,
.eyebrow {
  color: #6e675f;
}

.graph-header h2,
.eyebrow {
  margin: 0;
}

.graph-canvas {
  width: 100%;
  height: 30rem;
  border-radius: 1.15rem;
  background:
    radial-gradient(circle at top left, rgba(15, 118, 110, 0.08), transparent 24%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(248, 243, 233, 0.94));
  border: 1px solid rgba(31, 28, 24, 0.08);
}

.empty-state {
  padding: 1rem;
  border-radius: 1rem;
  border: 1px dashed rgba(31, 28, 24, 0.16);
  color: #6e675f;
}

.legend-dot {
  display: inline-block;
  width: 0.85rem;
  height: 0.85rem;
  margin-right: 0.35rem;
  border-radius: 999px;
  vertical-align: middle;
}

.legend-dot.agent { background: rgba(255, 255, 255, 0.95); border: 1px solid rgba(31, 28, 24, 0.22); }
.legend-dot.phase { background: rgba(245, 223, 180, 0.95); border: 1px solid rgba(188, 136, 67, 0.28); }
.legend-dot.round { background: rgba(226, 235, 248, 0.95); border: 1px solid rgba(92, 124, 174, 0.28); }

.graph-edge {
  stroke: rgba(29, 27, 25, 0.18);
  stroke-width: 1.5;
}

.edge-supports { stroke: rgba(15, 118, 110, 0.42); }
.edge-conflicts_with { stroke: rgba(173, 66, 51, 0.38); }
.edge-synthesized_into,
.edge-purchased_from,
.edge-settled_by { stroke: rgba(169, 111, 40, 0.4); }

.graph-node {
  cursor: pointer;
}

.graph-node circle {
  fill: rgba(255, 255, 255, 0.96);
  stroke: rgba(31, 28, 24, 0.14);
  stroke-width: 1.15;
}

.graph-node.phase circle {
  fill: rgba(249, 235, 204, 0.98);
}

.graph-node.debate_round circle {
  fill: rgba(232, 239, 250, 0.98);
}

.graph-node.selected circle,
.graph-node.active circle {
  stroke: rgba(24, 22, 19, 0.82);
  stroke-width: 2.2;
}

.node-title,
.node-meta {
  text-anchor: middle;
  pointer-events: none;
}

.node-title {
  font-size: 11px;
  font-weight: 700;
  fill: #1d1b19;
}

.node-meta {
  font-size: 9px;
  fill: #6e675f;
}
</style>
