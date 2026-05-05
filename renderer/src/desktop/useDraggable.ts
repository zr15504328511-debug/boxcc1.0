import { useRef, useState, useCallback } from 'react';

export interface Pos { x: number; y: number }

interface DragRef {
  startPointer: Pos;
  startPos: Pos;
}

/**
 * usePanelDrag — 适合「整个面板靠某个把手拖动」场景。
 * 调用方在 handle 元素上挂 startDrag。
 */
export function usePanelDrag(defaultPos: Pos) {
  const [pos, setPos] = useState<Pos>(defaultPos);
  const dragRef = useRef<DragRef | null>(null);

  const startDrag = useCallback((e: React.MouseEvent) => {
    if (e.button !== 0) return;
    e.stopPropagation();
    dragRef.current = {
      startPointer: { x: e.clientX, y: e.clientY },
      startPos: { ...pos },
    };
    const onMove = (ev: MouseEvent) => {
      if (!dragRef.current) return;
      const dx = ev.clientX - dragRef.current.startPointer.x;
      const dy = ev.clientY - dragRef.current.startPointer.y;
      const nx = clamp(dragRef.current.startPos.x + dx, -200, window.innerWidth - 60);
      const ny = clamp(dragRef.current.startPos.y + dy, 30, window.innerHeight - 30);
      setPos({ x: nx, y: ny });
    };
    const onUp = () => {
      dragRef.current = null;
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  }, [pos]);

  return { pos, setPos, startDrag };
}

/**
 * useButtonDrag — 适合「按钮可拖也可点」场景。
 * 鼠标按下后移动超过 threshold 视为拖动，否则当 click。
 */
export function useButtonDrag(defaultPos: Pos, onClick: () => void, threshold = 5) {
  const [pos, setPos] = useState<Pos>(defaultPos);
  const dragRef = useRef<{ start: Pos; pos: Pos; moved: boolean } | null>(null);

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    if (e.button !== 0) return;
    e.stopPropagation();
    dragRef.current = {
      start: { x: e.clientX, y: e.clientY },
      pos: { ...pos },
      moved: false,
    };
    const onMove = (ev: MouseEvent) => {
      if (!dragRef.current) return;
      const dx = ev.clientX - dragRef.current.start.x;
      const dy = ev.clientY - dragRef.current.start.y;
      if (!dragRef.current.moved && Math.hypot(dx, dy) < threshold) return;
      dragRef.current.moved = true;
      setPos({
        x: clamp(dragRef.current.pos.x + dx, 0, window.innerWidth - 60),
        y: clamp(dragRef.current.pos.y + dy, 30, window.innerHeight - 60),
      });
    };
    const onUp = () => {
      const moved = dragRef.current?.moved;
      dragRef.current = null;
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
      if (!moved) onClick();
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  }, [pos, onClick, threshold]);

  return { pos, setPos, onMouseDown };
}

function clamp(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, v));
}
