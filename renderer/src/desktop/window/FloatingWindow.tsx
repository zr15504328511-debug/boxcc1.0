import { useRef, type ReactNode } from 'react';
import { useWindowStore } from './windowStore';

interface Props {
  id: string;
  children: ReactNode;
}

export function FloatingWindow({ id, children }: Props) {
  const win = useWindowStore((s) => s.windows[id]);
  const close = useWindowStore((s) => s.close);
  const focus = useWindowStore((s) => s.focus);
  const setPosition = useWindowStore((s) => s.setPosition);
  const topId = useWindowStore((s) => s.topId());

  const dragRef = useRef<{ ox: number; oy: number; startX: number; startY: number } | null>(null);

  if (!win) return null;
  const focused = topId === id;

  const onTitleMouseDown = (e: React.MouseEvent) => {
    if (e.button !== 0) return;
    focus(id);
    dragRef.current = {
      ox: e.clientX,
      oy: e.clientY,
      startX: win.position.x,
      startY: win.position.y,
    };
    const onMove = (ev: MouseEvent) => {
      if (!dragRef.current) return;
      const dx = ev.clientX - dragRef.current.ox;
      const dy = ev.clientY - dragRef.current.oy;
      const nx = Math.max(0, Math.min(window.innerWidth - 80, dragRef.current.startX + dx));
      const ny = Math.max(28, Math.min(window.innerHeight - 80, dragRef.current.startY + dy));
      setPosition(id, { x: nx, y: ny });
    };
    const onUp = () => {
      dragRef.current = null;
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  };

  return (
    <div
      data-floating-window
      className={`absolute glass-window ${focused ? 'glass-window--focused' : ''} no-select`}
      style={{
        left: win.position.x,
        top: win.position.y,
        width: win.size.w,
        height: win.size.h,
        zIndex: win.z,
        opacity: focused ? 1 : 0.96,
      }}
      onMouseDown={(e) => { e.stopPropagation(); focus(id); }}
      onClick={(e) => e.stopPropagation()}
    >
      {/* Title bar */}
      <div
        className="h-9 px-4 flex items-center border-b border-white/5 cursor-grab active:cursor-grabbing"
        onMouseDown={onTitleMouseDown}
      >
        <div className="flex-1 text-[12px] font-medium text-desk-text/90 truncate">
          {win.title}
        </div>
        <div className="text-[10px] text-desk-faint">
          再次点击触发按钮 · 或点桌面关闭
        </div>
      </div>

      {/* Body */}
      <div className="overflow-hidden" style={{ height: 'calc(100% - 36px)' }}>
        {children}
      </div>
    </div>
  );
}
