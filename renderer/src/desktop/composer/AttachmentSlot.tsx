import { useState } from 'react';

interface Props {
  kind: 'file' | 'image';
  title: string;
}

export function AttachmentSlot({ kind, title }: Props) {
  const [hint, setHint] = useState(false);
  return (
    <button
      className="relative w-8 h-8 rounded-lg border border-white/8 bg-white/5 hover:bg-white/8 hover:border-white/15 transition flex items-center justify-center text-desk-faint hover:text-desk-dim"
      onMouseEnter={() => setHint(true)}
      onMouseLeave={() => setHint(false)}
      title={`${title}（即将推出）`}
      onClick={(e) => e.preventDefault()}
    >
      {kind === 'file' ? (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <path d="M14 2v6h6" />
        </svg>
      ) : (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
          <rect x="3" y="3" width="18" height="18" rx="2" />
          <circle cx="9" cy="9" r="2" />
          <path d="m21 15-5-5L5 21" />
        </svg>
      )}
      {hint && (
        <div className="absolute bottom-full mb-2 left-1/2 -translate-x-1/2 whitespace-nowrap text-[10.5px] px-2 py-1 rounded glass-card text-desk-dim">
          即将推出
        </div>
      )}
    </button>
  );
}
