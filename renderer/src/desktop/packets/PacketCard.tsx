import { useState, useEffect } from 'react';
import { useSessionStore } from '@/store/sessionStore';
import { useWindowStore } from '../window/windowStore';
import { usePacketStore } from './usePacketStore';
import { PACKET_KIND_ICON, PACKET_KIND_LABEL, type PacketCardState } from './packetTypes';

interface Props {
  packet: PacketCardState;
  index: number;
  total: number;
}

const KIND_ACCENT: Record<string, string> = {
  task_packet: '#7c9cff',
  worker_output: '#5dd29b',
  validation: '#f0b341',
  rework: '#ef6b6b',
  finalize: '#a3e068',
};

export function PacketCard({ packet, index }: Props) {
  const colorMap = useSessionStore((s) => s.bookmarkColors);
  const togglePin = usePacketStore((s) => s.pin);
  const remove = usePacketStore((s) => s.remove);
  const toggleWindow = useWindowStore((s) => s.toggle);

  // 从右侧书签起飞 → 中央悬停。书签估算位置 = (right ~ 78, top 50% +/- 60*idx)
  const [arrived, setArrived] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setArrived(true), 30);
    return () => clearTimeout(t);
  }, []);

  // 简单堆叠：每张卡按 index 错开
  const offsetX = index * 18;
  const offsetY = index * 14;
  const restRight = 140 + offsetX;
  const restTop = 100 + offsetY;

  const sourceColor = colorMap[packet.sourceAgentId] || '#9aa6b6';
  const targetColor = colorMap[packet.targetAgentId] || '#9aa6b6';
  const accent = KIND_ACCENT[packet.kind] || '#7c9cff';

  return (
    <div
      data-floating-window
      onMouseDown={(e) => e.stopPropagation()}
      onClick={(e) => e.stopPropagation()}
      style={{
        position: 'absolute',
        right: arrived ? restRight : 60,           // 起点贴右侧（书签处）
        top: arrived ? restTop : '50%',
        transform: arrived ? 'translateY(0) scale(1) rotate(0deg)' : 'translateY(-50%) scale(0.6) rotate(-8deg)',
        opacity: arrived ? 1 : 0,
        transition: 'right 700ms cubic-bezier(0.22, 1, 0.36, 1), top 700ms cubic-bezier(0.22, 1, 0.36, 1), transform 700ms cubic-bezier(0.22, 1, 0.36, 1), opacity 350ms ease-out',
        zIndex: 50 + index,
      }}
    >
      <div
        className="glass-card w-[280px] cursor-default"
        style={{ borderTopColor: accent, borderTopWidth: 2 }}
      >
        {/* header — source → target */}
        <div className="px-3 pt-2.5 pb-1.5 flex items-center gap-2">
          <span
            className="w-6 h-6 rounded-md flex items-center justify-center text-[10px] font-bold text-[#0b1020]"
            style={{ background: sourceColor }}
            title={packet.sourceAgentId}
          >
            {packet.sourceAgentId.slice(0, 3).toUpperCase()}
          </span>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-desk-faint">
            <path d="M5 12h14" />
            <polyline points="12 5 19 12 12 19" />
          </svg>
          <span
            className="w-6 h-6 rounded-md flex items-center justify-center text-[10px] font-bold text-[#0b1020]"
            style={{ background: targetColor }}
            title={packet.targetAgentId}
          >
            {packet.targetAgentId.slice(0, 3).toUpperCase()}
          </span>
          <span className="ml-auto text-[14px]" title={PACKET_KIND_LABEL[packet.kind]}>
            {PACKET_KIND_ICON[packet.kind]}
          </span>
        </div>

        {/* kind chip */}
        <div className="px-3 pb-1.5">
          <span className="desk-chip" style={{ borderColor: `${accent}55`, color: accent }}>
            {PACKET_KIND_LABEL[packet.kind]}
          </span>
        </div>

        {/* preview */}
        <div className="px-3 pb-2.5 text-[12px] text-desk-text/85 leading-relaxed line-clamp-3 min-h-[40px]">
          {packet.preview || '（暂无内容预览）'}
        </div>

        {/* footer */}
        <div className="px-3 py-1.5 border-t border-white/5 flex items-center justify-between text-[10.5px] text-desk-faint">
          <span>{new Date(packet.createdAt).toLocaleTimeString()}</span>
          <div className="flex items-center gap-1">
            <button
              className={`px-1.5 py-0.5 rounded hover:bg-white/8 ${packet.pinned ? 'text-desk-accent' : ''}`}
              onClick={() => togglePin(packet.id)}
              title={packet.pinned ? '取消钉住' : '钉住'}
            >
              {packet.pinned ? '★ 已钉' : '☆ 钉住'}
            </button>
            {packet.detailNodeId && (
              <button
                className="px-1.5 py-0.5 rounded hover:bg-white/8"
                onClick={() => toggleWindow('node-detail', { nodeId: packet.detailNodeId, title: packet.kind })}
                title="展开详情"
              >
                展开
              </button>
            )}
            <button
              className="px-1.5 py-0.5 rounded hover:bg-white/8 text-desk-faint hover:text-desk-danger"
              onClick={() => remove(packet.id)}
              title="关闭"
            >
              ✕
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
