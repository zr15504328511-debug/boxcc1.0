import type { NodeProps } from '@xyflow/react';
import type { RunNode } from '@/adapter/runGraph';
import { useSessionStore } from '@/store/sessionStore';
import { NodeShell } from './NodeShell';

const ACCENT_BY_AGENT: Record<string, string> = {
  dom: '#5ad1c4',
  pln: '#f0b341',
  ana: '#c39bff',
  cpy: '#ff8aae',
};

export default function WorkerNode({ id, data }: NodeProps & { data: any }) {
  const node = data as RunNode;
  const setInspector = useSessionStore((s) => s.setInspectorNode);
  const selected = useSessionStore((s) => s.inspectorNodeId === id);
  const accent = ACCENT_BY_AGENT[node.agentId || ''] || '#7c9cff';
  const last = node.streamLog[node.streamLog.length - 1];
  const preview = node.latestOutput?.slice(0, 60) || last?.summary || '等待任务包';
  return (
    <NodeShell
      title={node.title}
      subtitle={`worker · ${node.agentId}`}
      status={node.status}
      accent={accent}
      selected={selected}
      onClick={() => setInspector(id)}
    >
      <div className="line-clamp-2 text-desk-text/80">{preview}</div>
    </NodeShell>
  );
}
