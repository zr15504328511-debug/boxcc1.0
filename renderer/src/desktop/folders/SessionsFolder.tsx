import { useState } from 'react';
import { useSessionStore, selectActiveGraph } from '@/store/sessionStore';

function formatTime(iso?: string): string {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
  } catch { return iso; }
}

export function SessionsFolder() {
  const sessions = useSessionStore((s) => s.sessions);
  const activeId = useSessionStore((s) => s.activeSessionId);
  const select = useSessionStore((s) => s.selectSession);
  const newSession = useSessionStore((s) => s.newSession);
  const rename = useSessionStore((s) => s.renameSession);
  const remove = useSessionStore((s) => s.deleteSession);
  const graphsBySession = useSessionStore((s) => s.graphsBySession);
  const _activeGraph = useSessionStore(selectActiveGraph); // ensure subscription updates

  const [editing, setEditing] = useState<string | null>(null);

  return (
    <div className="h-full flex flex-col">
      <div className="px-4 py-2.5 border-b border-white/5 flex items-center justify-between">
        <div className="text-[11px] text-desk-dim">
          共 <span className="text-desk-text font-medium">{sessions.length}</span> 个会话
        </div>
        <button className="desk-btn text-[11px]" onClick={() => newSession()}>+ 新会话</button>
      </div>

      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-2">
        {sessions.length === 0 && (
          <div className="px-2 py-8 text-center text-[12px] text-desk-faint">
            还没有会话。
          </div>
        )}
        {sessions.map((s) => {
          const active = s.id === activeId;
          const g = graphsBySession[s.id]?.graph;
          const nodeCount = g ? Object.keys(g.nodes).length : 0;
          const lastStatus = g?.status || 'idle';
          return (
            <div
              key={s.id}
              onClick={() => select(s.id)}
              onDoubleClick={() => setEditing(s.id)}
              className={`group relative px-3 py-2.5 rounded-xl cursor-pointer transition border ${
                active
                  ? 'bg-white/8 border-desk-accent/40 shadow-[0_0_0_1px_rgba(124,156,255,0.20)_inset]'
                  : 'bg-white/3 border-white/6 hover:bg-white/6'
              }`}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  {editing === s.id ? (
                    <input
                      autoFocus
                      defaultValue={s.title}
                      className="desk-input text-[12px] py-1"
                      onBlur={(e) => { rename(s.id, e.target.value || s.title); setEditing(null); }}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') (e.target as HTMLInputElement).blur();
                        if (e.key === 'Escape') setEditing(null);
                      }}
                      onClick={(e) => e.stopPropagation()}
                    />
                  ) : (
                    <div className="text-[12.5px] font-medium text-desk-text truncate">
                      {s.title || '未命名会话'}
                    </div>
                  )}
                  <div className="flex items-center gap-2 mt-1.5 text-[10.5px] text-desk-faint">
                    <span>{formatTime(s.updatedAt || s.createdAt)}</span>
                    {nodeCount > 0 && <span>· {nodeCount} 节点</span>}
                    {lastStatus !== 'idle' && (
                      <span className={
                        lastStatus === 'failed' ? 'text-desk-danger'
                        : lastStatus === 'running' ? 'text-desk-accent'
                        : 'text-desk-ok'
                      }>
                        · {lastStatus === 'completed' ? '已完成' : lastStatus === 'running' ? '运行中' : '失败'}
                      </span>
                    )}
                  </div>
                </div>
                <button
                  className="text-[10.5px] text-desk-faint opacity-0 group-hover:opacity-100 hover:text-desk-danger px-1"
                  onClick={(e) => {
                    e.stopPropagation();
                    if (confirm(`删除会话「${s.title || s.id}」？`)) remove(s.id);
                  }}
                >
                  删除
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
