import { useState } from 'react';
import { useSessionStore } from '@/store/sessionStore';

export function SessionDock() {
  const sessions = useSessionStore((s) => s.sessions);
  const activeId = useSessionStore((s) => s.activeSessionId);
  const select = useSessionStore((s) => s.selectSession);
  const newSession = useSessionStore((s) => s.newSession);
  const rename = useSessionStore((s) => s.renameSession);
  const remove = useSessionStore((s) => s.deleteSession);

  const [editingId, setEditingId] = useState<string | null>(null);

  return (
    <aside className="w-[220px] shrink-0 border-r border-desk-border bg-desk-panel/40 backdrop-blur flex flex-col">
      <div className="px-3 py-2 border-b border-desk-border flex items-center justify-between">
        <div className="text-[11px] uppercase tracking-wider text-desk-dim">会话</div>
        <button className="desk-btn text-[11px] py-0.5" onClick={() => newSession()}>
          + 新建
        </button>
      </div>
      <div className="flex-1 overflow-y-auto py-1">
        {sessions.length === 0 && (
          <div className="px-3 py-2 text-[11px] text-desk-dim">暂无会话</div>
        )}
        {sessions.map((s) => {
          const active = s.id === activeId;
          return (
            <div
              key={s.id}
              onClick={() => select(s.id)}
              onDoubleClick={() => setEditingId(s.id)}
              className={`group px-3 py-2 cursor-pointer border-l-2 ${
                active ? 'bg-desk-panel2 border-desk-accent' : 'border-transparent hover:bg-desk-panel2/60'
              }`}
            >
              {editingId === s.id ? (
                <input
                  autoFocus
                  defaultValue={s.title}
                  onBlur={(e) => {
                    rename(s.id, e.target.value || s.title);
                    setEditingId(null);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') (e.target as HTMLInputElement).blur();
                    if (e.key === 'Escape') setEditingId(null);
                  }}
                  className="desk-input text-[12px] py-1"
                />
              ) : (
                <div className="flex items-center justify-between gap-2">
                  <div className="text-[12px] truncate">{s.title || '未命名'}</div>
                  <button
                    className="text-[10px] text-desk-dim opacity-0 group-hover:opacity-100 hover:text-desk-danger"
                    onClick={(e) => {
                      e.stopPropagation();
                      if (confirm('删除该会话？')) remove(s.id);
                    }}
                  >
                    删除
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </aside>
  );
}
