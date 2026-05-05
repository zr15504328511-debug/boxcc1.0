import { useState, useRef } from 'react';
import { useSessionStore, selectActiveGraph } from '@/store/sessionStore';
import { useWindowStore } from '../window/windowStore';
import { HoverStatusCard } from './HoverStatusCard';
import { ColorMenu } from './ColorMenu';
import type { BookmarkSpec } from './agentRoster';
import { nodeIdFor } from '@/adapter/runGraph';
import { colorForAgent } from '@/theme/tokens';

const STATUS_DOT: Record<string, string> = {
  idle: 'node-dot node-dot--idle',
  running: 'node-dot node-dot--running',
  completed: 'node-dot node-dot--completed',
  failed: 'node-dot node-dot--failed',
};

function nodeIdFromSel(sel: BookmarkSpec['nodeIdSel']): string {
  if (sel === 'user') return nodeIdFor.user();
  if (sel === 'orc') return nodeIdFor.orc();
  if (sel === 'final') return nodeIdFor.final();
  if (sel.startsWith('critic:')) return nodeIdFor.critic(sel.split(':')[1]);
  if (sel.startsWith('worker:')) return nodeIdFor.worker(sel.split(':')[1]);
  return sel;
}

export function AgentBookmark({ spec }: { spec: BookmarkSpec }) {
  const graph = useSessionStore(selectActiveGraph);
  const colors = useSessionStore((s) => s.bookmarkColors);
  const color = colorForAgent(spec.agentId, colors);
  const setColor = useSessionStore((s) => s.setBookmarkColor);
  const toggleWindow = useWindowStore((s) => s.toggle);
  const detailOpen = useWindowStore((s) => !!s.windows[`node-detail:${nodeIdFromSel(spec.nodeIdSel)}`]);

  const [hover, setHover] = useState(false);
  const [colorMenuRect, setColorMenuRect] = useState<{ right: number; top: number } | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  const nodeId = nodeIdFromSel(spec.nodeIdSel);
  const node = graph.nodes[nodeId];
  const exists = !!node;
  const status = node?.status || 'idle';
  const dotClass = STATUS_DOT[status] || STATUS_DOT.idle;

  const onClick = () => {
    if (!exists) return;
    toggleWindow('node-detail', { nodeId, title: spec.label });
  };

  const onContextMenu = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const rect = ref.current?.getBoundingClientRect();
    if (!rect) return;
    setColorMenuRect({ right: window.innerWidth - rect.left + 8, top: rect.top });
  };

  return (
    <div
      ref={ref}
      className="relative"
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      onMouseDown={(e) => e.stopPropagation()}
    >
      {/* 书签本体 */}
      <button
        onClick={onClick}
        onContextMenu={onContextMenu}
        disabled={!exists}
        title={exists ? `${spec.label} — 单击展开 · 右键改色` : `${spec.label}（本次未激活）`}
        className={`relative flex flex-col items-center justify-center w-[58px] h-[58px] rounded-l-xl transition-all ${
          exists
            ? 'cursor-pointer hover:translate-x-[-4px]'
            : 'cursor-default opacity-35'
        } ${detailOpen ? 'translate-x-[-6px]' : ''}`}
        style={{
          background: exists
            ? `linear-gradient(180deg, ${color}E6, ${color}B3)`
            : 'rgba(255,255,255,0.04)',
          boxShadow: exists
            ? `0 4px 14px rgba(0,0,0,0.35), 0 0 0 1px rgba(255,255,255,0.18) inset, -3px 0 0 0 ${color}`
            : '0 0 0 1px rgba(255,255,255,0.06) inset',
        }}
      >
        <div
          className="bookmark-text text-[12px] font-bold tracking-wide"
          style={{ color: exists ? '#0b1020' : 'rgba(154,166,182,0.7)' }}
        >
          {spec.shortLabel}
        </div>
        {exists && (
          <div className="bookmark-text absolute bottom-1.5 right-1.5">
            <span className={dotClass} style={{ width: 5, height: 5 }} />
          </div>
        )}
      </button>

      {/* hover 状态卡，向左浮出 */}
      {hover && exists && !colorMenuRect && (
        <div className="absolute right-full top-0 mr-3 z-[300]">
          <HoverStatusCard
            agentLabel={spec.label}
            description={spec.description}
            color={color}
            node={node}
          />
        </div>
      )}

      {/* 颜色菜单（右键唤出，不依赖 hover） */}
      {colorMenuRect && (
        <>
          <div
            className="fixed inset-0 z-[399]"
            onMouseDown={() => setColorMenuRect(null)}
          />
          <ColorMenu
            agentId={spec.agentId}
            currentHex={color}
            onPick={(hex) => setColor(spec.agentId, hex)}
            onClose={() => setColorMenuRect(null)}
            anchorRect={colorMenuRect}
          />
        </>
      )}
    </div>
  );
}
