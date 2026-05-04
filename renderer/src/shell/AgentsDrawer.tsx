import { useSessionStore } from '@/store/sessionStore';

const PHASE_LABEL: Record<string, string> = {
  lead: '主席团',
  worker: '部门 worker',
  critic: '质检 critic',
};

export function AgentsDrawer() {
  const agents = useSessionStore((s) => s.agents);
  const saveAgents = useSessionStore((s) => s.saveAgents);
  const setDrawer = useSessionStore((s) => s.setDrawer);

  const grouped = agents.reduce<Record<string, typeof agents>>((acc, a) => {
    const k = a.phase || 'worker';
    (acc[k] ||= []).push(a);
    return acc;
  }, {});

  return (
    <div className="h-full flex flex-col">
      <div className="px-4 py-3 border-b border-desk-border flex items-center justify-between">
        <div>
          <div className="text-base font-semibold">部门资源</div>
          <div className="text-[11px] text-desk-dim mt-0.5">配置来源：backend/config.yaml</div>
        </div>
        <button className="desk-btn text-[11px]" onClick={() => setDrawer(null)}>关闭</button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-5">
        {Object.entries(grouped).map(([phase, list]) => (
          <section key={phase}>
            <div className="desk-label mb-2">{PHASE_LABEL[phase] || phase}</div>
            <div className="space-y-2">
              {list.map((a) => (
                <div key={a.id} className="desk-card p-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="text-[13px] font-semibold truncate">{a.name}</div>
                      <div className="text-[11px] text-desk-dim font-mono">{a.id}</div>
                    </div>
                    <label className="flex items-center gap-1 text-[11px] text-desk-dim">
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
                    <div className="text-[11px] text-desk-dim mt-2 leading-relaxed">
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
              ))}
            </div>
          </section>
        ))}
        {agents.length === 0 && (
          <div className="text-[12px] text-desk-dim">未加载到 agents。请确认后端在线。</div>
        )}
      </div>
    </div>
  );
}
