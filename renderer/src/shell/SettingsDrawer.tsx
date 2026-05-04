import { useState } from 'react';
import { useSessionStore } from '@/store/sessionStore';
import type { ProfileSpec } from '@/types/boxccApi';

function uid() {
  return `pf-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
}

export function SettingsDrawer() {
  const profiles = useSessionStore((s) => s.profiles);
  const providers = useSessionStore((s) => s.providers);
  const activeProfileId = useSessionStore((s) => s.activeProfileId);
  const saveProfiles = useSessionStore((s) => s.saveProfiles);
  const setActiveProfile = useSessionStore((s) => s.setActiveProfile);
  const refreshModelsFor = useSessionStore((s) => s.refreshModelsFor);
  const setDrawer = useSessionStore((s) => s.setDrawer);

  const [refreshing, setRefreshing] = useState<string | null>(null);

  const upsert = (next: ProfileSpec) => {
    const list = profiles.some((p) => p.id === next.id)
      ? profiles.map((p) => (p.id === next.id ? next : p))
      : [...profiles, next];
    saveProfiles(list);
  };

  const remove = (id: string) => {
    const list = profiles.filter((p) => p.id !== id);
    saveProfiles(list);
    if (activeProfileId === id) setActiveProfile(list[0]?.id || null);
  };

  const addProfile = () => {
    const provider = providers[0]?.id || 'openai';
    const fresh: ProfileSpec = {
      id: uid(),
      provider,
      label: '新配置',
      baseUrl: providers[0]?.default_base_url || '',
      apiKey: '',
      model: '',
      models: [],
    };
    upsert(fresh);
    setActiveProfile(fresh.id);
  };

  return (
    <div className="h-full flex flex-col">
      <div className="px-4 py-3 border-b border-desk-border flex items-center justify-between">
        <div>
          <div className="text-base font-semibold">模型配置</div>
          <div className="text-[11px] text-desk-dim mt-0.5">使用现有 IPC 后端，仅迁移入口位置。</div>
        </div>
        <button className="desk-btn text-[11px]" onClick={() => setDrawer(null)}>关闭</button>
      </div>

      <div className="px-4 py-3 border-b border-desk-border flex items-center justify-between gap-2">
        <select
          className="desk-input text-[12px]"
          value={activeProfileId || ''}
          onChange={(e) => setActiveProfile(e.target.value || null)}
        >
          {profiles.length === 0 && <option value="">（无）</option>}
          {profiles.map((p) => (
            <option key={p.id} value={p.id}>
              {p.label || p.provider} · {p.model || '未选模型'}
            </option>
          ))}
        </select>
        <button className="desk-btn text-[11px]" onClick={addProfile}>+ 新建</button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {profiles.length === 0 && (
          <div className="text-[12px] text-desk-dim">
            还没有任何模型配置。点击右上「+ 新建」开始。
          </div>
        )}
        {profiles.map((p) => (
          <div key={p.id} className={`desk-card p-3 space-y-2 ${activeProfileId === p.id ? 'ring-1 ring-desk-accent' : ''}`}>
            <div className="flex items-center justify-between">
              <input
                className="desk-input text-[12px] py-1"
                value={p.label || ''}
                onChange={(e) => upsert({ ...p, label: e.target.value })}
                placeholder="配置名"
              />
              <button className="text-[11px] text-desk-danger ml-2" onClick={() => remove(p.id)}>删除</button>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div>
                <div className="desk-label mb-1">provider</div>
                <select
                  className="desk-input text-[12px] py-1"
                  value={p.provider}
                  onChange={(e) => {
                    const next = providers.find((x) => x.id === e.target.value);
                    upsert({
                      ...p,
                      provider: e.target.value,
                      baseUrl: next?.default_base_url || p.baseUrl,
                    });
                  }}
                >
                  {providers.map((pv) => (
                    <option key={pv.id} value={pv.id}>{pv.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <div className="desk-label mb-1">model</div>
                {p.models && p.models.length > 0 ? (
                  <select
                    className="desk-input text-[12px] py-1"
                    value={p.model || ''}
                    onChange={(e) => upsert({ ...p, model: e.target.value })}
                  >
                    <option value="">（选择）</option>
                    {p.models.map((m) => (
                      <option key={m} value={m}>{m}</option>
                    ))}
                  </select>
                ) : (
                  <input
                    className="desk-input text-[12px] py-1"
                    value={p.model || ''}
                    onChange={(e) => upsert({ ...p, model: e.target.value })}
                    placeholder="模型名"
                  />
                )}
              </div>
            </div>

            <div>
              <div className="desk-label mb-1">base url</div>
              <input
                className="desk-input text-[12px] py-1"
                value={p.baseUrl || ''}
                onChange={(e) => upsert({ ...p, baseUrl: e.target.value })}
                placeholder="https://api.example.com/v1"
              />
            </div>
            <div>
              <div className="desk-label mb-1">api key</div>
              <input
                type="password"
                className="desk-input text-[12px] py-1"
                value={p.apiKey || ''}
                onChange={(e) => upsert({ ...p, apiKey: e.target.value })}
                placeholder="sk-..."
              />
            </div>

            <div className="flex items-center justify-between pt-1">
              <button
                className="desk-btn text-[11px] py-1"
                disabled={refreshing === p.id}
                onClick={async () => {
                  setRefreshing(p.id);
                  try { await refreshModelsFor(p.id); } finally { setRefreshing(null); }
                }}
              >
                {refreshing === p.id ? '刷新中...' : '刷新模型列表'}
              </button>
              {activeProfileId !== p.id && (
                <button className="desk-btn-primary text-[11px] py-1" onClick={() => setActiveProfile(p.id)}>
                  设为当前
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
