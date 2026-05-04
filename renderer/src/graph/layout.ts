import dagre from 'dagre';
import type { RunGraph } from '@/adapter/runGraph';

const NODE_W = 240;
const NODE_H = 110;

export function computeLayout(
  graph: RunGraph,
  overrides: Record<string, { x: number; y: number }> = {},
): Record<string, { x: number; y: number }> {
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: 'LR', nodesep: 50, ranksep: 100, marginx: 40, marginy: 40 });
  g.setDefaultEdgeLabel(() => ({}));

  for (const id of Object.keys(graph.nodes)) {
    g.setNode(id, { width: NODE_W, height: NODE_H });
  }
  for (const e of Object.values(graph.edges)) {
    if (graph.nodes[e.source] && graph.nodes[e.target]) {
      g.setEdge(e.source, e.target);
    }
  }

  dagre.layout(g);

  const out: Record<string, { x: number; y: number }> = {};
  for (const id of Object.keys(graph.nodes)) {
    if (overrides[id]) {
      out[id] = overrides[id];
      continue;
    }
    const dn = g.node(id);
    if (!dn) continue;
    out[id] = { x: dn.x - NODE_W / 2, y: dn.y - NODE_H / 2 };
  }
  return out;
}
