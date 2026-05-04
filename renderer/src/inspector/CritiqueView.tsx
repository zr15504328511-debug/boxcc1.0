import type { ValidationReport } from '@/adapter/runGraph';

const GATE_COLOR: Record<string, string> = {
  passed: 'text-desk-ok',
  fixes_required: 'text-desk-warn',
  failed: 'text-desk-danger',
  unknown: 'text-desk-dim',
};

export function CritiqueView({ report }: { report?: ValidationReport }) {
  if (!report) {
    return <div className="text-[12px] text-desk-dim">尚未生成质检结论。</div>;
  }
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <span className="desk-label">pass_gate</span>
        <span className={`text-[12px] font-semibold ${GATE_COLOR[report.pass_gate]}`}>
          {report.pass_gate}
        </span>
      </div>
      {report.summary && (
        <div>
          <div className="desk-label mb-1">summary</div>
          <div className="text-[12px] leading-relaxed whitespace-pre-wrap">{report.summary}</div>
        </div>
      )}
      {report.rework_targets && report.rework_targets.length > 0 && (
        <div>
          <div className="desk-label mb-1">rework targets</div>
          <ul className="space-y-1.5">
            {report.rework_targets.map((t, i) => (
              <li key={i} className="desk-card p-2">
                <div className="text-[11px] text-desk-dim">{t.owner}</div>
                <div className="text-[12px] leading-relaxed">{t.summary}</div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
