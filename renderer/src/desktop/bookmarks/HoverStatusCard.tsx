import type { RunNode } from '@/adapter/runGraph';

interface Props {
  agentLabel: string;
  description: string;
  color: string;
  node?: RunNode;
}

const STATUS_LABEL: Record<string, string> = {
  idle: '待运行',
  running: '运行中',
  completed: '已完成',
  failed: '失败',
  needs_rework: '需返工',
  reworking: '返工中',
  validated: '已通过',
  timed_out: '超时',
};

const STATUS_DOT: Record<string, string> = {
  idle: 'node-dot node-dot--idle',
  running: 'node-dot node-dot--running',
  completed: 'node-dot node-dot--completed',
  failed: 'node-dot node-dot--failed',
};

function oneLineFor(node?: RunNode): string {
  if (!node) return '尚未运行';
  if (node.errorMessage) return node.errorMessage;
  // 取最后一条 streamLog 的 summary 或 title
  const last = node.streamLog?.[node.streamLog.length - 1];
  if (last?.summary) return last.summary;
  if (last?.title) return last.title;
  if (node.latestOutput) return node.latestOutput.slice(0, 80);
  if (node.status === 'completed') return '步骤已完成';
  if (node.status === 'running') return '正在执行…';
  return '等待任务包';
}

export function HoverStatusCard({ agentLabel, description, color, node }: Props) {
  const status = node?.status || 'idle';
  return (
    <div
      className="glass-card px-3 py-2.5 w-[260px] pointer-events-none"
      style={{ borderLeftColor: color, borderLeftWidth: 3 }}
    >
      <div className="flex items-center gap-2 mb-1.5">
        <span className={STATUS_DOT[status] || 'node-dot node-dot--idle'} />
        <div className="text-[12.5px] font-semibold text-desk-text">{agentLabel}</div>
        <span className="ml-auto text-[10.5px] text-desk-faint">{STATUS_LABEL[status] || status}</span>
      </div>
      <div className="text-[10.5px] text-desk-faint mb-1.5">{description}</div>
      <div className="text-[12px] text-desk-text/85 leading-relaxed line-clamp-3">
        {oneLineFor(node)}
      </div>
    </div>
  );
}
