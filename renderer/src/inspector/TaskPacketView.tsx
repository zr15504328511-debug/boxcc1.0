import type { WorkerTaskPacket } from '@/adapter/runGraph';

function Section({ title, items }: { title: string; items?: string[] }) {
  if (!items || items.length === 0) return null;
  return (
    <div>
      <div className="desk-label mb-1">{title}</div>
      <ul className="space-y-1">
        {items.map((it, i) => (
          <li key={i} className="text-[12px] leading-relaxed text-desk-text/85 pl-3 relative">
            <span className="absolute left-0 top-2 w-1 h-1 rounded-full bg-desk-accent" />
            {it}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function TaskPacketView({ packet }: { packet?: WorkerTaskPacket }) {
  if (!packet) {
    return <div className="text-[12px] text-desk-dim">该节点暂无任务包。</div>;
  }
  return (
    <div className="space-y-3">
      {packet.objective && (
        <div>
          <div className="desk-label mb-1">objective</div>
          <div className="text-[12px] leading-relaxed">{packet.objective}</div>
        </div>
      )}
      {packet.task && (
        <div>
          <div className="desk-label mb-1">task</div>
          <div className="text-[12px] leading-relaxed whitespace-pre-wrap">{packet.task}</div>
        </div>
      )}
      <Section title="context" items={packet.context} />
      <Section title="constraints" items={packet.constraints} />
      <Section title="required_output" items={packet.required_output} />
      <Section title="success_criteria" items={packet.success_criteria} />
      <Section title="requested_skill_packs" items={packet.requested_skill_packs} />
      <Section title="notes" items={packet.notes} />
    </div>
  );
}
