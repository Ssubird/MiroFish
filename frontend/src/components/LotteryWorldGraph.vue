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
          <path d="M0,0 L7,3.5 L0,7 z" fill="rgba(255, 255, 255, 0.45)" />
        </marker>
        <filter id="neon-glow" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur in="SourceGraphic" stdDeviation="3" result="blur1" />
          <feGaussianBlur in="SourceGraphic" stdDeviation="6" result="blur2" />
          <feMerge>
            <feMergeNode in="blur2" />
            <feMergeNode in="blur1" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        <filter id="neon-glow-strong" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur in="SourceGraphic" stdDeviation="4" result="blur1" />
          <feGaussianBlur in="SourceGraphic" stdDeviation="15" result="blur2" />
          <feMerge>
            <feMergeNode in="blur2" />
            <feMergeNode in="blur1" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      <!-- Draw edges first so they sit behind nodes -->
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

      <!-- Draw nodes -->
      <g
        v-for="node in layout.nodes"
        :key="node.id"
        class="graph-node"
        :class="[node.node_type, { selected: node.id === selectedNodeId, active: node.active }]"
        @click="$emit('select-node', node.id)"
      >
        <title>{{ node.label }} ({{ node.meta }})</title>

        <!-- Node Hover Aura -->
        <circle class="node-aura" :cx="node.x" :cy="node.y" :r="node.radius + 15" />

        <!-- Selected Crosshair targeting -->
        <g v-if="node.id === selectedNodeId" class="crosshairs" filter="url(#neon-glow-strong)">
          <path :d="`M ${node.x - node.radius - 12} ${node.y} L ${node.x - node.radius - 4} ${node.y}`" />
          <path :d="`M ${node.x + node.radius + 12} ${node.y} L ${node.x + node.radius + 4} ${node.y}`" />
          <path :d="`M ${node.x} ${node.y - node.radius - 12} L ${node.x} ${node.y - node.radius - 4}`" />
          <path :d="`M ${node.x} ${node.y + node.radius + 12} L ${node.x} ${node.y + node.radius - 4}`" />
          <circle class="crosshair-ring" :cx="node.x" :cy="node.y" :r="node.radius + 8" />
        </g>

        <!-- Outer Orbital Ring -->
        <circle class="node-ring" :cx="node.x" :cy="node.y" :r="node.radius + 2" />
        
        <!-- Inner Core -->
        <circle class="node-core" :cx="node.x" :cy="node.y" :r="node.radius - 2" filter="url(#neon-glow)" />

        <text :x="node.x" :y="node.y + node.radius + 20" class="node-title">{{ node.label }}</text>
        <text :x="node.x" :y="node.y + node.radius + 33" class="node-meta">{{ node.meta }}</text>
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
      radius: 20,
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
      radius: 17,
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
      y: 300 + row * 66,
      radius: 14,
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
  gap: 1.25rem;
  padding: 1.35rem;
  border-radius: 1.5rem;
  border: 1px solid rgba(0, 240, 255, 0.15);
  background: rgba(11, 12, 16, 0.6);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  box-shadow: 0 20px 48px rgba(0, 0, 0, 0.5), inset 0 0 20px rgba(0, 240, 255, 0.05);
  color: #e0e6ed;
}

.graph-header,
.graph-metrics,
.graph-legend {
  display: flex;
  gap: 1.25rem;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
}

.graph-metrics,
.graph-legend,
.eyebrow {
  color: #8b9bb4;
}

.graph-header h2,
.eyebrow {
  margin: 0;
}

.graph-header h2 {
  font-size: 1.6rem;
  font-weight: 700;
  color: #fff;
  letter-spacing: 0.02em;
}

.graph-metrics span {
  background: rgba(0, 240, 255, 0.1);
  border: 1px solid rgba(0, 240, 255, 0.2);
  padding: 0.35rem 0.9rem;
  border-radius: 999px;
  color: #00f0ff;
  font-size: 0.95rem;
  font-weight: 600;
  box-shadow: inset 0 0 8px rgba(0, 240, 255, 0.1);
  letter-spacing: 0.05em;
}

.graph-canvas {
  width: 100%;
  height: 34rem;
  border-radius: 1.25rem;
  background:
    radial-gradient(circle at center, rgba(0, 240, 255, 0.05), transparent 60%),
    linear-gradient(180deg, #0b0c10, #15161d);
  border: 1px solid rgba(255, 255, 255, 0.08);
  box-shadow: inset 0 0 40px rgba(0, 0, 0, 0.5);
  position: relative;
  overflow: hidden;
}

.graph-canvas::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  background-image: 
    linear-gradient(rgba(0, 240, 255, 0.05) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0, 240, 255, 0.05) 1px, transparent 1px);
  background-size: 30px 30px;
  pointer-events: none;
}

.empty-state {
  padding: 3rem 1rem;
  text-align: center;
  border-radius: 1rem;
  border: 1px dashed rgba(0, 240, 255, 0.4);
  background: rgba(0, 240, 255, 0.03);
  color: #8b9bb4;
  font-size: 1.1rem;
}

.legend-dot {
  display: inline-block;
  width: 0.9rem;
  height: 0.9rem;
  margin-right: 0.4rem;
  border-radius: 999px;
  vertical-align: middle;
  box-shadow: 0 0 10px currentColor;
}

.legend-dot.agent { background: #00f0ff; color: rgba(0, 240, 255, 0.8); border: 1px solid #fff; }
.legend-dot.phase { background: #ffd700; color: rgba(255, 215, 0, 0.8); border: 1px solid #fff; }
.legend-dot.round { background: #b020f0; color: rgba(176, 32, 240, 0.8); border: 1px solid #fff; }

.graph-legend span {
  display: flex;
  align-items: center;
  font-size: 0.95rem;
  font-weight: 500;
  color: #e0e6ed;
}

.graph-edge {
  stroke: rgba(255, 255, 255, 0.25);
  stroke-width: 1.5;
  transition: all 0.3s ease;
}

.edge-supports { stroke: rgba(0, 240, 255, 0.5); stroke-dasharray: 4, 3; }
.edge-conflicts_with { stroke: rgba(255, 60, 60, 0.6); stroke-dasharray: 8, 4; }
.edge-synthesized_into,
.edge-purchased_from,
.edge-settled_by { stroke: rgba(255, 180, 0, 0.5); }

.graph-node {
  cursor: pointer;
}

.node-aura {
  fill: transparent;
  stroke: transparent;
  stroke-width: 1;
  transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
  pointer-events: all;
}

.node-ring {
  fill: rgba(11, 12, 16, 0.8);
  stroke-width: 1.5;
  stroke-dasharray: 4, 2;
  transition: all 0.3s ease;
  transform-origin: center;
}

.node-core {
  fill: rgba(255, 255, 255, 0.05);
  stroke-width: 2;
  transition: all 0.3s ease;
}

@keyframes spin { 100% { transform: rotate(360deg); } }
@keyframes pulse { 0%, 100% { transform: scale(1); opacity: 0.8; } 50% { transform: scale(1.1); opacity: 1; }}

/* Agent Node */
.graph-node.agent .node-ring { stroke: #00f0ff; animation: spin 20s linear infinite; }
.graph-node.agent .node-core { stroke: #fff; fill: rgba(0, 240, 255, 0.2); }

/* Phase Node */
.graph-node.phase .node-ring { stroke: #ffd700; stroke-dasharray: none; }
.graph-node.phase .node-core { stroke: #fff; fill: rgba(255, 215, 0, 0.2); animation: pulse 3s infinite ease-in-out; }

/* Debate Node */
.graph-node.debate_round .node-ring { stroke: #b020f0; stroke-dasharray: 6, 6; animation: spin 15s linear infinite reverse; }
.graph-node.debate_round .node-core { stroke: #fff; fill: rgba(176, 32, 240, 0.2); }

/* Hover States */
.graph-node:hover .node-aura {
  fill: rgba(255, 255, 255, 0.05);
  stroke: rgba(255, 255, 255, 0.3);
  stroke-dasharray: 2, 4;
}

.graph-node:hover .node-core {
  fill: rgba(255, 255, 255, 0.4);
  stroke-width: 3;
}

/* Selected States with Crosshairs */
.crosshairs path {
  stroke: #fff;
  stroke-width: 1.5;
  stroke-linecap: round;
}

.crosshair-ring {
  fill: transparent;
  stroke: #fff;
  stroke-width: 1;
  stroke-dasharray: 2, 6;
  animation: spin 10s linear infinite;
}

.graph-node.selected .node-core {
  fill: rgba(255, 255, 255, 0.8);
  stroke-width: 4;
}

.graph-node.selected.agent .crosshairs { stroke: #00f0ff; }
.graph-node.selected.phase .crosshairs { stroke: #ffd700; }
.graph-node.selected.debate_round .crosshairs { stroke: #b020f0; }

.node-title,
.node-meta {
  text-anchor: middle;
  pointer-events: none;
  font-family: 'Inter', sans-serif;
}

.node-title {
  font-size: 13px;
  font-weight: 700;
  fill: #fff;
  text-shadow: 0 2px 6px rgba(0, 0, 0, 1), 0 0 10px rgba(255, 255, 255, 0.4);
}

.node-meta {
  font-size: 10px;
  font-weight: 500;
  fill: #00f0ff;
  text-shadow: 0 1px 3px rgba(0, 0, 0, 1);
  letter-spacing: 0.05em;
}
</style>
