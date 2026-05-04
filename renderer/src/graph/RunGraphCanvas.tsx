import { useMemo, useEffect, useState } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  ReactFlowProvider,
  type Node,
  type Edge,
  type NodeChange,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { useSessionStore, selectActiveGraph, selectActivePositions } from '@/store/sessionStore';
import { computeLayout } from './layout';
import UserRequestNode from './nodes/UserRequestNode';
import OrcNode from './nodes/OrcNode';
import WorkerNode from './nodes/WorkerNode';
import CriticNode from './nodes/CriticNode';
import ArtifactNode from './nodes/ArtifactNode';
import FlowEdge from './edges/FlowEdge';

const nodeTypes = {
  user: UserRequestNode as any,
  orc: OrcNode as any,
  worker: WorkerNode as any,
  critic: CriticNode as any,
  artifact: ArtifactNode as any,
};

const edgeTypes = {
  flow: FlowEdge as any,
};

export function RunGraphCanvas() {
  const graph = useSessionStore(selectActiveGraph);
  const positions = useSessionStore(selectActivePositions);
  const setNodePosition = useSessionStore((s) => s.setNodePosition);

  const [localPositions, setLocalPositions] = useState<Record<string, { x: number; y: number }>>(positions);

  // 当 graph 节点集变化时，重新布局；用户已拖动过的节点位置保留。
  useEffect(() => {
    const layout = computeLayout(graph, positions);
    setLocalPositions(layout);
  }, [graph.nodes, graph.edges, positions]);

  const nodes: Node[] = useMemo(() => {
    return Object.values(graph.nodes).map((n) => ({
      id: n.id,
      type: n.type,
      position: localPositions[n.id] || { x: 0, y: 0 },
      data: n as unknown as Record<string, unknown>,
      draggable: true,
      connectable: false,
    }));
  }, [graph.nodes, localPositions]);

  const edges: Edge[] = useMemo(() => {
    return Object.values(graph.edges).map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      type: 'flow',
      data: { status: e.status, type: e.type },
      label: e.label,
      animated: e.status === 'active',
    }));
  }, [graph.edges]);

  const handleNodesChange = (changes: NodeChange[]) => {
    for (const change of changes) {
      const c = change as Extract<NodeChange, { type: 'position' }>;
      if (c.type !== 'position' || !c.position) continue;
      if (c.dragging) {
        setLocalPositions((p) => ({ ...p, [c.id]: c.position! }));
      } else {
        setNodePosition(c.id, c.position);
      }
    }
  };

  const isEmpty = Object.keys(graph.nodes).length === 0;

  return (
    <div className="relative h-full w-full">
      <ReactFlowProvider>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          onNodesChange={handleNodesChange}
          fitView
          fitViewOptions={{ padding: 0.2, duration: 200 }}
          nodesConnectable={false}
          elementsSelectable
          proOptions={{ hideAttribution: true }}
        >
          <Background gap={24} size={1} color="#1c222b" />
          <Controls position="bottom-right" showInteractive={false} />
          <MiniMap
            position="bottom-left"
            pannable
            zoomable
            maskColor="rgba(0,0,0,0.5)"
            nodeColor={(n) => {
              const t = (n.data as any)?.type;
              if (t === 'orc') return '#7c9cff';
              if (t === 'worker') return '#5ad1c4';
              if (t === 'critic') return '#f0b341';
              if (t === 'artifact') return '#6cd17a';
              return '#9aa6b2';
            }}
          />
        </ReactFlow>
      </ReactFlowProvider>

      {isEmpty && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="text-center text-desk-dim">
            <div className="text-base font-medium">空白桌面</div>
            <div className="text-sm mt-1">在底部输入框给 orc 发一个任务，节点会按编排顺序出现。</div>
          </div>
        </div>
      )}
    </div>
  );
}
