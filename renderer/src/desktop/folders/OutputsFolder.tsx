import { useRef } from 'react';
import { useFilesStore, type FileItem } from './filesStore';

const ICON_BY_KIND: Record<string, React.ReactNode> = {
  doc: (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <path d="M14 2v6h6" />
      <line x1="16" y1="13" x2="8" y2="13" />
      <line x1="16" y1="17" x2="8" y2="17" />
    </svg>
  ),
  image: (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <circle cx="9" cy="9" r="2" />
      <path d="m21 15-5-5L5 21" />
    </svg>
  ),
  sheet: (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <line x1="3" y1="9" x2="21" y2="9" />
      <line x1="3" y1="15" x2="21" y2="15" />
      <line x1="9" y1="3" x2="9" y2="21" />
      <line x1="15" y1="3" x2="15" y2="21" />
    </svg>
  ),
  note: (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
  ),
};

const ACCENT_BY_KIND: Record<string, string> = {
  doc: '#7c9cff',
  image: '#5ad1c4',
  sheet: '#f0b341',
  note: '#c39bff',
};

export function OutputsFolder() {
  const files = useFilesStore((s) => s.files);
  const list = Object.values(files);

  return (
    <div className="h-full flex flex-col">
      {/* header */}
      <div className="px-4 py-3 border-b border-white/5 flex items-center justify-between">
        <div>
          <div className="text-[10px] uppercase tracking-wider text-desk-faint">files</div>
          <div className="text-[14px] font-semibold text-desk-text mt-0.5">产物文件夹</div>
        </div>
        <div className="text-[10.5px] text-desk-faint">
          {list.length} 个文件 · 拖动排列
        </div>
      </div>

      {/* canvas */}
      <FolderCanvas />
    </div>
  );
}

function FolderCanvas() {
  const files = useFilesStore((s) => s.files);
  const list = Object.values(files);

  return (
    <div className="relative flex-1 overflow-auto">
      {/* 空态引导 */}
      {list.length === 0 && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="text-center px-6 max-w-[360px]">
            <div className="text-[48px] mb-3 opacity-30">📁</div>
            <div className="text-[13px] font-semibold text-desk-text mb-1.5">空文件夹</div>
            <div className="text-[11.5px] text-desk-faint leading-relaxed">
              这里只放真实文件。<br/>
              附件 / 图片 / 表格 / 笔记功能将在下一版接入；<br/>
              文件可在画布内自由拖动排列。
            </div>
            <div className="mt-4 inline-block desk-chip">即将推出</div>
          </div>
        </div>
      )}

      {/* 文件卡 */}
      {list.map((f) => (
        <FileCard key={f.id} file={f} />
      ))}
    </div>
  );
}

function FileCard({ file }: { file: FileItem }) {
  const setPosition = useFilesStore((s) => s.setPosition);
  const remove = useFilesStore((s) => s.remove);
  const dragRef = useRef<{ ox: number; oy: number; sx: number; sy: number } | null>(null);

  const accent = ACCENT_BY_KIND[file.kind] || '#7c9cff';
  const icon = ICON_BY_KIND[file.kind];

  const onMouseDown = (e: React.MouseEvent) => {
    if (e.button !== 0) return;
    e.stopPropagation();
    dragRef.current = {
      ox: e.clientX,
      oy: e.clientY,
      sx: file.position.x,
      sy: file.position.y,
    };
    const onMove = (ev: MouseEvent) => {
      if (!dragRef.current) return;
      const dx = ev.clientX - dragRef.current.ox;
      const dy = ev.clientY - dragRef.current.oy;
      setPosition(file.id, {
        x: Math.max(0, dragRef.current.sx + dx),
        y: Math.max(0, dragRef.current.sy + dy),
      });
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
      style={{ left: file.position.x, top: file.position.y }}
      className="absolute flex flex-col items-center w-[80px] cursor-grab active:cursor-grabbing group"
      onMouseDown={onMouseDown}
    >
      <div
        className="w-14 h-14 rounded-xl flex items-center justify-center"
        style={{
          background: `linear-gradient(180deg, ${accent}E6, ${accent}99)`,
          color: '#0b1020',
          boxShadow: '0 4px 14px rgba(0,0,0,0.4), 0 0 0 1px rgba(255,255,255,0.18) inset',
        }}
      >
        {icon}
      </div>
      <div
        className="text-[10.5px] mt-1.5 px-1.5 py-0.5 rounded text-desk-text text-center max-w-full truncate"
        style={{ textShadow: '0 1px 2px rgba(0,0,0,0.6)' }}
      >
        {file.name}
      </div>
      <button
        className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-desk-danger text-white text-[10px] opacity-0 group-hover:opacity-100 hover:brightness-110 flex items-center justify-center"
        onClick={(e) => { e.stopPropagation(); remove(file.id); }}
        onMouseDown={(e) => e.stopPropagation()}
        title="删除"
      >
        ×
      </button>
    </div>
  );
}
