import { useSessionStore } from '@/store/sessionStore';
import { useWindowStore } from './window/windowStore';

export function MenuBar() {
  const session = useSessionStore((s) => s.sessions.find((x) => x.id === s.activeSessionId));
  const sessionCount = useSessionStore((s) => s.sessions.length);
  const errorMessage = useSessionStore((s) => s.errorMessage);
  const status = useSessionStore((s) => s.status);
  const toggleWindow = useWindowStore((s) => s.toggle);
  const sessionsOpen = useWindowStore((s) => !!s.windows['sessions']);

  return (
    <div
      className="absolute top-0 left-0 right-0 h-7 px-3 glass-menubar flex items-center gap-2 text-[11.5px] z-[1000] no-select"
      onMouseDown={(e) => e.stopPropagation()}
    >
      <div className="font-semibold tracking-wide text-desk-text">boxcc</div>

      {/* 会话入口紧贴 boxcc 右侧 */}
      <button
        onClick={(e) => { e.stopPropagation(); toggleWindow('sessions'); }}
        className={`group flex items-center gap-1.5 px-2 py-0.5 rounded transition ${
          sessionsOpen
            ? 'bg-white/10 text-desk-text'
            : 'hover:bg-white/8 text-desk-dim hover:text-desk-text'
        }`}
        title={`会话 (${sessionCount}) — 再次点击关闭`}
      >
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="3" y="5" width="18" height="14" rx="2" />
          <path d="M3 9h18" />
        </svg>
        <span className="truncate max-w-[260px]">
          {session?.title || '未命名会话'}
        </span>
        <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="opacity-50 group-hover:opacity-100">
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      <div className="flex-1" />

      {/* 仅在出错时显示错误徽章 */}
      {status === 'error' && errorMessage && (
        <div className="flex items-center gap-1.5 text-desk-danger px-2 py-0.5 rounded bg-desk-danger/10 border border-desk-danger/20">
          <span className="node-dot node-dot--failed" />
          <span className="truncate max-w-[280px]">{errorMessage}</span>
        </div>
      )}
    </div>
  );
}
