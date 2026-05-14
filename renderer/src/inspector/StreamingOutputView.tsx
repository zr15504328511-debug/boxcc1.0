import type { RunNode } from '@/adapter/runGraph';

export function StreamingOutputView({ node }: { node: RunNode }) {
  const log = node.streamLog || [];
  return (
    <div className="space-y-2">
      <div className="desk-label">过程日志</div>
      {log.length === 0 ? (
        <div className="text-[12px] text-desk-dim">暂无过程事件。</div>
      ) : (
        <ul className="space-y-1.5">
          {log.map((e, i) => (
            <li key={i} className="text-[11px] leading-relaxed text-desk-text/80 flex gap-2">
              <span className="text-desk-dim shrink-0 w-14">
                {new Date(e.ts).toLocaleTimeString()}
              </span>
              <span>
                {e.title && <span className="font-medium text-desk-text">{e.title} · </span>}
                {e.summary || (e.status ?? '')}
              </span>
            </li>
          ))}
        </ul>
      )}
      {node.errorMessage && (
        <div className="mt-2 text-[12px] text-desk-danger bg-desk-danger/10 border border-desk-danger/30 rounded p-2">
          {node.errorMessage}
        </div>
      )}
    </div>
  );
}
