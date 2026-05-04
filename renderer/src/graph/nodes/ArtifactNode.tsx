import type { NodeProps } from '@xyflow/react';
import type { RunNode } from '@/adapter/runGraph';
import { useSessionStore } from '@/store/sessionStore';
import { NodeShell } from './NodeShell';

export default function ArtifactNode({ id, data }: NodeProps & { data: any }) {
  const node = data as RunNode;
  const setInspector = useSessionStore((s) => s.setInspectorNode);
  const selected = useSessionStore((s) => s.inspectorNodeId === id);
  const preview = node.latestOutput?.slice(0, 80) || '汇总中...';
  return (
    <NodeShell
      title={node.title}
      subtitle="final · artifact"
      status={node.status}
      accent="#6cd17a"
      selected={selected}
      showSourceHandle={false}
      onClick={() => setInspector(id)}
    >
      <div className="line-clamp-2 text-desk-text/80">{preview}</div>
    </NodeShell>
  );
}
