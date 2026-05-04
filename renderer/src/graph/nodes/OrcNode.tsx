import type { NodeProps } from '@xyflow/react';
import type { RunNode } from '@/adapter/runGraph';
import { useSessionStore } from '@/store/sessionStore';
import { NodeShell } from './NodeShell';

export default function OrcNode({ id, data }: NodeProps & { data: any }) {
  const node = data as RunNode;
  const setInspector = useSessionStore((s) => s.setInspectorNode);
  const selected = useSessionStore((s) => s.inspectorNodeId === id);
  const last = node.streamLog[node.streamLog.length - 1];
  return (
    <NodeShell
      title={node.title}
      subtitle="编排 / 路由"
      status={node.status}
      accent="#7c9cff"
      selected={selected}
      onClick={() => setInspector(id)}
    >
      <div className="line-clamp-2">{last?.summary || last?.title || '等待用户任务'}</div>
    </NodeShell>
  );
}
