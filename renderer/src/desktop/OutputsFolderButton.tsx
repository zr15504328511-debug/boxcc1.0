import { useWindowStore } from './window/windowStore';
import { useFilesStore } from './folders/filesStore';
import { useButtonDrag } from './useDraggable';

const SIZE = 48;
function defaultPos() {
  return { x: window.innerWidth - SIZE - 24, y: window.innerHeight - SIZE - 24 };
}

export function OutputsFolderButton() {
  const toggleWindow = useWindowStore((s) => s.toggle);
  const open = useWindowStore((s) => !!s.windows['outputs']);
  const fileCount = useFilesStore((s) => Object.keys(s.files).length);

  const { pos, onMouseDown } = useButtonDrag(defaultPos(), () => toggleWindow('outputs'));

  return (
    <button
      onMouseDown={onMouseDown}
      title={`产物文件夹 (${fileCount}) — 拖动调整位置 · 点击打开`}
      style={{ left: pos.x, top: pos.y, width: SIZE, height: SIZE }}
      className={`absolute z-[200] glass-composer rounded-2xl flex items-center justify-center cursor-grab active:cursor-grabbing transition ${
        open ? 'text-desk-accent ring-1 ring-desk-accent/60' : 'text-desk-text hover:text-white'
      }`}
    >
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
        <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
      </svg>
      {fileCount > 0 && (
        <span className="absolute -top-1 -right-1 min-w-[18px] h-[18px] px-1 rounded-full bg-desk-accent text-[10px] font-bold text-[#0b1020] flex items-center justify-center">
          {fileCount}
        </span>
      )}
    </button>
  );
}
