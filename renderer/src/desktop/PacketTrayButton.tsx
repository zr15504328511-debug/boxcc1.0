import { useRef } from 'react';
import { usePacketStore } from './packets/usePacketStore';

/**
 * MenuBar 右侧按钮：toggle 通信卡片显隐 + 显示 packet 数量。
 * 长按 ≥600ms → 清除全部（含已钉住）。
 */
export function PacketTrayButton() {
  const visible = usePacketStore((s) => s.visible);
  const count = usePacketStore((s) => Object.keys(s.packets).length);
  const toggleVisible = usePacketStore((s) => s.toggleVisible);
  const removeAll = usePacketStore((s) => s.removeAll);

  const longPressTimer = useRef<number | null>(null);
  const longPressed = useRef(false);

  const onMouseDown = () => {
    longPressed.current = false;
    longPressTimer.current = window.setTimeout(() => {
      longPressed.current = true;
      if (count === 0) return;
      if (confirm(`清除全部 ${count} 张通信卡片？（含已钉住）`)) {
        removeAll();
      }
    }, 600);
  };
  const cancelTimer = () => {
    if (longPressTimer.current) {
      clearTimeout(longPressTimer.current);
      longPressTimer.current = null;
    }
  };
  const onMouseUp = (e: React.MouseEvent) => {
    cancelTimer();
    if (longPressed.current) return;
    e.stopPropagation();
    toggleVisible();
  };

  const dimmed = !visible || count === 0;

  return (
    <button
      onMouseDown={(e) => { e.stopPropagation(); onMouseDown(); }}
      onMouseUp={onMouseUp}
      onMouseLeave={cancelTimer}
      onContextMenu={(e) => {
        e.preventDefault();
        e.stopPropagation();
        if (count === 0) return;
        if (confirm(`清除全部 ${count} 张通信卡片？（含已钉住）`)) removeAll();
      }}
      title={
        count === 0
          ? '通信卡片 — 暂无消息'
          : visible
          ? `通信卡片 (${count}) — 点击隐藏 · 长按清除`
          : `通信卡片 (${count}) — 点击召回 · 长按清除`
      }
      className={`group relative flex items-center gap-1.5 px-2 py-0.5 rounded transition ${
        dimmed
          ? 'text-desk-faint hover:text-desk-dim hover:bg-white/5'
          : 'bg-desk-accent/15 text-desk-text hover:bg-desk-accent/25'
      }`}
    >
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M22 12h-6l-2 3h-4l-2-3H2" />
        <path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z" />
      </svg>
      <span className="font-mono text-[11px] tabular-nums">
        {count}
      </span>
      {!visible && count > 0 && (
        <span className="absolute -top-0.5 -right-0.5 w-1.5 h-1.5 rounded-full bg-desk-accent" />
      )}
    </button>
  );
}
