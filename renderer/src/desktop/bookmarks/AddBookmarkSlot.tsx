import { useState } from 'react';

export function AddBookmarkSlot() {
  const [hint, setHint] = useState(false);
  return (
    <div
      className="relative"
      onMouseEnter={() => setHint(true)}
      onMouseLeave={() => setHint(false)}
      onMouseDown={(e) => e.stopPropagation()}
    >
      <button
        title="添加新部门 — 即将推出"
        onClick={() => {
          alert(
            '添加新部门：\n\n当前 MVP 通过编辑 backend/config.yaml 在 agents: 列表中添加新条目即可，重启后会自动出现在书签里。\nGUI 添加面板将在后续版本提供。',
          );
        }}
        className="relative flex flex-col items-center justify-center w-[58px] h-[58px] rounded-l-xl cursor-pointer transition hover:translate-x-[-4px]"
        style={{
          background: 'rgba(255,255,255,0.04)',
          border: '1px dashed rgba(255,255,255,0.18)',
          borderRight: 'none',
        }}
      >
        <div className="bookmark-text text-[20px] font-light text-desk-faint leading-none">+</div>
      </button>

      {hint && (
        <div className="absolute right-full top-0 mr-3 z-[300] glass-card px-3 py-2 w-[220px] pointer-events-none">
          <div className="text-[12px] font-semibold text-desk-text mb-1">添加部门</div>
          <div className="text-[11px] text-desk-dim leading-relaxed">
            目前在 <span className="font-mono text-desk-text">backend/config.yaml</span> 添加 agent 条目，重启后自动出现。GUI 添加面板下版本支持。
          </div>
        </div>
      )}
    </div>
  );
}
