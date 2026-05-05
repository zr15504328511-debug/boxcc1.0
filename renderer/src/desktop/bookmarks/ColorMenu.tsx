import { BOOKMARK_PALETTE } from '@/theme/tokens';

interface Props {
  agentId: string;
  currentHex: string;
  onPick: (hex: string) => void;
  onClose: () => void;
  anchorRect: { right: number; top: number };
}

export function ColorMenu({ agentId, currentHex, onPick, onClose, anchorRect }: Props) {
  return (
    <div
      data-floating-window
      className="glass-card p-2 w-[220px] absolute z-[400]"
      style={{ right: anchorRect.right + 64, top: anchorRect.top }}
      onMouseDown={(e) => e.stopPropagation()}
      onClick={(e) => e.stopPropagation()}
    >
      <div className="text-[10px] uppercase tracking-wider text-desk-faint mb-2 px-1">
        {agentId} · 选颜色
      </div>
      <div className="grid grid-cols-4 gap-1.5">
        {BOOKMARK_PALETTE.map((c) => {
          const active = c.hex.toLowerCase() === currentHex.toLowerCase();
          return (
            <button
              key={c.id}
              title={c.name}
              onClick={() => { onPick(c.hex); onClose(); }}
              className={`relative h-9 rounded-md transition hover:scale-105 ${
                active ? 'ring-2 ring-white' : 'ring-1 ring-white/10'
              }`}
              style={{ background: c.hex }}
            >
              {active && (
                <svg
                  width="14" height="14" viewBox="0 0 24 24"
                  className="absolute inset-0 m-auto text-[#0b1020]"
                  fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"
                >
                  <polyline points="20 6 9 17 4 12" />
                </svg>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
