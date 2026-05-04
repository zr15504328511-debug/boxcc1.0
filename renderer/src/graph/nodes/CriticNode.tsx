import type { NodeProps } from '@xyflow/react';
import type { RunNode } from '@/adapter/runGraph';
import { useSessionStore } from '@/store/sessionStore';
import { NodeShell } from './NodeShell';

const GATE_LABEL: Record<string, string> = {
  passed: '通过',
  fixes_required: '需修正',
  failed: '失败',
  unknown: '审查中',
};

export default function CriticNode({ id, data }: NodeProps & { data: any }) {
  const node = data as RunNode;
  const setInspector = useSessionStore((s) => s.setInspectorNode);
  const selected = useSessionStore((s) => s.inspectorNodeId === id);
  const gate = node.validation?.pass_gate || 'unknown';
  const summary = node.validation?.summary || node.streamLog[node.streamLog.length - 1]?.summary;
  return (
    <NodeShell
      title={node.title}
      subtitle="critic · 质检"
      status={node.status}
      accent="#f0b341"
      selected={selected}
      onClick={() => setInspector(id)}
    >
      <div className="flex items-center gap-2 mb-1">
        <span className="desk-chip" style={{ color: gate === 'passed' ? '#6cd17a' : gate === 'failed' ? '#ef6b6b' : '#f0b341' }}>
          {GATE_LABEL[gate] || gate}
        </span>
        {(node.validation?.rework_targets?.length ?? 0) > 0 && (
          <span className="desk-chip">{node.validation!.rework_targets!.length} 项待修</span>
        )}
      </div>
      <div className="line-clamp-2 text-desk-text/80">{summary || '等待 worker 输出'}</div>
    </NodeShell>
  );
}
