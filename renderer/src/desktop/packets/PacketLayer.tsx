import { usePacketStore } from './usePacketStore';
import { usePacketEvents } from './usePacketEvents';
import { PacketCard } from './PacketCard';

export function PacketLayer() {
  // 监听 graph，把通信事件灌入 store
  usePacketEvents();

  const packets = usePacketStore((s) => s.packets);
  const visible = usePacketStore((s) => s.visible);
  const list = Object.values(packets).sort((a, b) => a.createdAt - b.createdAt);

  if (!visible) return null;

  return (
    <div className="absolute inset-0 pointer-events-none">
      {list.map((p, idx) => (
        <div key={p.id} style={{ pointerEvents: 'auto' }}>
          <PacketCard packet={p} index={idx} total={list.length} />
        </div>
      ))}
    </div>
  );
}
