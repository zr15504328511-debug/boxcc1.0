import { Handle, Position } from '@xyflow/react';
import type { RunNodeStatus } from '@/adapter/runGraph';

interface Props {
  title: string;
  subtitle?: string;
  status: RunNodeStatus;
  accent: string;
  selected?: boolean;
  showSourceHandle?: boolean;
  showTargetHandle?: boolean;
  children?: React.ReactNode;
  onClick?: () => void;
}

const STATUS_LABEL: Record<RunNodeStatus, string> = {
  idle: '待运行',
  running: '运行中',
  completed: '已完成',
  failed: '失败',
  needs_rework: '需返工',
  reworking: '返工中',
  validated: '已通过',
  timed_out: '超时',
};

const STATUS_DOT_CLASS: Record<RunNodeStatus, string> = {
  idle: 'node-status-dot node-status-idle',
  running: 'node-status-dot node-status-running',
  completed: 'node-status-dot node-status-completed',
  failed: 'node-status-dot node-status-failed',
  needs_rework: 'node-status-dot node-status-running',
  reworking: 'node-status-dot node-status-running',
  validated: 'node-status-dot node-status-completed',
  timed_out: 'node-status-dot node-status-failed',
};

export function NodeShell({
  title,
  subtitle,
  status,
  accent,
  selected,
  showSourceHandle = true,
  showTargetHandle = true,
  children,
  onClick,
}: Props) {
  const ring = selected ? 'ring-2 ring-desk-accent' : 'ring-0';
  const failedRing = status === 'failed' ? 'ring-1 ring-desk-danger/60' : '';
  return (
    <div
      onClick={onClick}
      className={`desk-card w-[240px] cursor-pointer select-none transition ${ring} ${failedRing}`}
      style={{ borderTopColor: accent, borderTopWidth: 2 }}
    >
      {showTargetHandle && <Handle type="target" position={Position.Left} isConnectable={false} />}
      <div className="px-3 py-2 border-b border-desk-border flex items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="text-[12px] font-semibold truncate">{title}</div>
          {subtitle && <div className="text-[10px] text-desk-dim truncate">{subtitle}</div>}
        </div>
        <div className="flex items-center gap-1.5">
          <span className={STATUS_DOT_CLASS[status]} />
          <span className="text-[10px] text-desk-dim">{STATUS_LABEL[status]}</span>
        </div>
      </div>
      <div className="px-3 py-2 text-[11px] text-desk-dim min-h-[44px]">{children}</div>
      {showSourceHandle && <Handle type="source" position={Position.Right} isConnectable={false} />}
    </div>
  );
}
