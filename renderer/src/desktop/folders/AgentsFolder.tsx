import { useSessionStore } from '@/store/sessionStore';
import { agentColor } from '@/theme/tokens';

const PHASE_LABEL: Record<string, string> = {
  lead: '主席团',
  worker: '部门 worker',
  critic: '质检 critic',
};

const PHASE_ORDER = ['lead', 'worker', 'critic'];

export function AgentsFolder() {
  const agents = useSessionStore((s) => s.agents);
  const saveAgents = useSessionStore((s) => s.saveAgents);

  const grouped = agents.reduce<Record<string, typeof agents>>((acc, a) => {
    const k = a.phase || 'worker';
    (acc[k] ||= []).push(a);
    return acc;
  }, {});

  return (
    <div className="h-full overflow-y-auto px-5 py-4 space-y-5">
      {PHASE_ORDER.filter((p) => grouped[p]).map((phase) => (
        <section key={phase}>
          <div className="desk-label mb-2.5">{PHASE_LABEL[phase] || phase}</div>
          <div className="space-y-2">
            {grouped[phase].map((a) => {
              const color = agentColor(a.id);
              return (
                <div key={a.id} className="glass-card p-3 flex gap-3">
                  <div
                    className="shrink-0 w-9 h-9 rounded-lg flex items-center justify-center font-mono text-[12px] font-bold text-[#0b1020]"
                    style={{ background: `linear-gradient(135deg, ${color}, ${color}cc)` }}
                  >
                    {a.id.slice(0, 3).toUpperCase()}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="text-[13px] font-semibold text-desk-text truncate">{a.name}</div>
                        <div className="text-[10.5px] text-desk-faint font-mono">{a.id}</div>
                      </div>
                      <label className="flex items-center gap-1 text-[10.5px] text-desk-dim shrink-0">
                        <input
                          type="checkbox"
                          checked={a.enabled !== false}
                          onChange={(e) => {
                            const next = agents.map((x) =>
                              x.id === a.id ? { ...x, enabled: e.target.checked } : x,
                            );
                            saveAgents(next);
                          }}
                        />
                        启用
                      </label>
                    </div>
                    {(a.description || a.desc) && (
                      <div className="text-[11.5px] text-desk-dim mt-1.5 leading-relaxed line-clamp-3">
                        {a.description || a.desc}
                      </div>
                    )}
                    {a.skill_packs && a.skill_packs.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-2">
                        {a.skill_packs.map((sp) => (
                          <span key={sp} className="desk-chip">{sp}</span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      ))}
      {agents.length === 0 && (
        <div className="text-[12px] text-desk-faint pt-8 text-center">
          未加载到 agents。请确认后端在线。
        </div>
      )}
    </div>
  );
}
