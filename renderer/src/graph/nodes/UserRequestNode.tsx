import type { NodeProps } from '@xyflow/react';
import type { RunNode } from '@/adapter/runGraph';
import { useSessionStore } from '@/store/sessionStore';
import { NodeShell } from './NodeShell';

export default function UserRequestNode({ id, data }: NodeProps & { data: any }) {
  const node = data as RunNode;
  const setInspector = useSessionStore((s) => s.setInspectorNode);
  const selected = useSessionStore((s) => s.inspectorNodeId === id);
  const text = (node.latestOutput || '').trim();
  return (
    <NodeShell
      title={node.title}
      subtitle="user_request"
      status={node.status}
      accent="#7c9cff"
      selected={selected}
      showTargetHandle={false}
      onClick={() => setInspector(id)}
    >
      <div className="line-clamp-3 text-desk-text/80">{text || '（空）'}</div>
    </NodeShell>
  );
}
