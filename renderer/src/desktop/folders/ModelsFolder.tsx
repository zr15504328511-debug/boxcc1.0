import { useState } from 'react';
import { useSessionStore } from '@/store/sessionStore';
import type { ProfileSpec } from '@/types/boxccApi';

function uid() {
  return `pf-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
}

export function ModelsFolder() {
  const profiles = useSessionStore((s) => s.profiles);
  const providers = useSessionStore((s) => s.providers);
  const activeProfileId = useSessionStore((s) => s.activeProfileId);
  const saveProfiles = useSessionStore((s) => s.saveProfiles);
  const setActiveProfile = useSessionStore((s) => s.setActiveProfile);
  const refreshModelsFor = useSessionStore((s) => s.refreshModelsFor);

  const [refreshing, setRefreshing] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(activeProfileId);

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
    setOpenId(fresh.id);
  };

  const editing = profiles.find((p) => p.id === openId);

  return (
    <div className="h-full flex flex-col">
      {/* toolbar */}
      <div className="px-4 py-2.5 border-b border-white/5 flex items-center justify-between">
        <div className="text-[11px] text-desk-dim">
          已配置 <span className="text-desk-text font-medium">{profiles.length}</span> 个 profile
        </div>
        <button className="desk-btn text-[11px]" onClick={addProfile}>
          + 新建
        </button>
      </div>

      <div className="flex-1 flex min-h-0">
        {/* left: profile list */}
        <div className="w-[180px] border-r border-white/5 overflow-y-auto py-2">
          {profiles.length === 0 && (
            <div className="px-3 py-2 text-[11.5px] text-desk-faint">
              尚无配置。点击右上「+ 新建」开始。
            </div>
          )}
          {profiles.map((p) => {
            const active = p.id === activeProfileId;
            const open = p.id === openId;
            return (
              <div
                key={p.id}
                onClick={() => setOpenId(p.id)}
                className={`mx-2 my-1 px-2.5 py-2 rounded-lg cursor-pointer transition ${
                  open ? 'bg-white/8 ring-1 ring-white/15' : 'hover:bg-white/4'
                }`}
              >
                <div className="flex items-center justify-between gap-1">
                  <div className="text-[12px] truncate text-desk-text">{p.label || '未命名'}</div>
                  {active && <span className="node-dot node-dot--running" />}
                </div>
                <div className="text-[10.5px] text-desk-faint truncate mt-0.5 font-mono">
                  {p.provider} / {p.model || '—'}
                </div>
              </div>
            );
          })}
        </div>

        {/* right: editor */}
        <div className="flex-1 overflow-y-auto px-5 py-4">
          {!editing && (
            <div className="text-[12px] text-desk-faint pt-8 text-center">
              选择一个配置查看 / 编辑
            </div>
          )}
          {editing && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <input
                  className="desk-input text-[13px] py-1.5 max-w-[260px]"
                  value={editing.label || ''}
                  onChange={(e) => upsert({ ...editing, label: e.target.value })}
                  placeholder="配置名"
                />
                <button className="text-[11px] text-desk-danger hover:underline" onClick={() => remove(editing.id)}>
                  删除配置
                </button>
              </div>

              <div>
                <div className="desk-label mb-1.5">provider</div>
                <select
                  className="desk-input text-[12px] py-1.5"
                  value={editing.provider}
                  onChange={(e) => {
                    const next = providers.find((x) => x.id === e.target.value);
                    upsert({
                      ...editing,
                      provider: e.target.value,
                      baseUrl: next?.default_base_url || editing.baseUrl,
                    });
                  }}
                >
                  {providers.map((pv) => (
                    <option key={pv.id} value={pv.id}>{pv.label}</option>
                  ))}
                </select>
              </div>

              <div>
                <div className="desk-label mb-1.5">base url</div>
                <input
                  className="desk-input text-[12px] py-1.5 font-mono"
                  value={editing.baseUrl || ''}
                  onChange={(e) => upsert({ ...editing, baseUrl: e.target.value })}
                  placeholder="https://api.example.com/v1"
                />
              </div>

              <div>
                <div className="desk-label mb-1.5">api key</div>
                <input
                  type="password"
                  className="desk-input text-[12px] py-1.5 font-mono"
                  value={editing.apiKey || ''}
                  onChange={(e) => upsert({ ...editing, apiKey: e.target.value })}
                  placeholder="sk-..."
                />
              </div>

              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <div className="desk-label">model</div>
                  <button
                    className="text-[10.5px] text-desk-dim hover:text-desk-text"
                    disabled={refreshing === editing.id}
                    onClick={async () => {
                      setRefreshing(editing.id);
                      try { await refreshModelsFor(editing.id); } finally { setRefreshing(null); }
                    }}
                  >
                    {refreshing === editing.id ? '刷新中…' : '↻ 刷新模型列表'}
                  </button>
                </div>
                {editing.models && editing.models.length > 0 ? (
                  <select
                    className="desk-input text-[12px] py-1.5"
                    value={editing.model || ''}
                    onChange={(e) => upsert({ ...editing, model: e.target.value })}
                  >
                    <option value="">（选择）</option>
                    {editing.models.map((m) => (
                      <option key={m} value={m}>{m}</option>
                    ))}
                  </select>
                ) : (
                  <input
                    className="desk-input text-[12px] py-1.5 font-mono"
                    value={editing.model || ''}
                    onChange={(e) => upsert({ ...editing, model: e.target.value })}
                    placeholder="模型名"
                  />
                )}
              </div>

              <div className="pt-2 flex items-center gap-2">
                {activeProfileId === editing.id ? (
                  <span className="desk-chip text-desk-ok">已设为当前</span>
                ) : (
                  <button className="desk-btn-primary text-[12px]" onClick={() => setActiveProfile(editing.id)}>
                    设为当前
                  </button>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
