import { useSessionStore } from '@/store/sessionStore';

export function TopBar() {
  const session = useSessionStore((s) =>
    s.sessions.find((x) => x.id === s.activeSessionId),
  );
  const status = useSessionStore((s) => s.status);
  const errorMessage = useSessionStore((s) => s.errorMessage);
  const setDrawer = useSessionStore((s) => s.setDrawer);
  const drawer = useSessionStore((s) => s.drawer);

  const statusLabel = status === 'running' ? '运行中' : status === 'error' ? '失败' : '空闲';
  const statusClass =
    status === 'running' ? 'text-desk-accent' : status === 'error' ? 'text-desk-danger' : 'text-desk-dim';

  return (
    <header className="h-11 px-4 flex items-center justify-between border-b border-desk-border bg-desk-panel/60 backdrop-blur">
      <div className="flex items-center gap-3">
        <div className="font-mono text-sm font-bold tracking-wide">boxcc</div>
        <span className="desk-chip">节点工作桌面</span>
        {session && <span className="text-[12px] text-desk-dim truncate max-w-[280px]">{session.title}</span>}
      </div>
      <div className="flex items-center gap-2">
        <div className="flex items-center gap-1.5 text-[11px]">
          <span className={`node-status-dot ${status === 'running' ? 'node-status-running' : status === 'error' ? 'node-status-failed' : 'node-status-idle'}`} />
          <span className={statusClass}>{statusLabel}</span>
          {errorMessage && <span className="text-desk-danger ml-1">· {errorMessage}</span>}
        </div>
        <button
          className={`desk-btn text-[11px] py-1 ${drawer === 'agents' ? 'text-white border-desk-accent' : ''}`}
          onClick={() => setDrawer(drawer === 'agents' ? null : 'agents')}
        >
          部门
        </button>
        <button
          className={`desk-btn text-[11px] py-1 ${drawer === 'settings' ? 'text-white border-desk-accent' : ''}`}
          onClick={() => setDrawer(drawer === 'settings' ? null : 'settings')}
        >
          模型
        </button>
      </div>
    </header>
  );
}
