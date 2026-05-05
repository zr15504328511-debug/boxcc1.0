import { create } from 'zustand';
import type { PacketCardState } from './packetTypes';

interface PacketStore {
  packets: Record<string, PacketCardState>;
  visible: boolean;
  upsert: (p: PacketCardState) => void;
  pin: (id: string) => void;
  remove: (id: string) => void;
  clearUnpinned: () => void;
  removeAll: () => void;
  reset: () => void;
  toggleVisible: () => void;
  hide: () => void;
  show: () => void;
}

export const usePacketStore = create<PacketStore>((set) => ({
  packets: {},
  visible: true,

  upsert: (p) => set((s) => {
    const existing = s.packets[p.id];
    if (existing) {
      // 已存在则只更新可变字段，保留位置和 pinned
      if (existing.preview === p.preview && existing.title === p.title) return s;
      return {
        packets: {
          ...s.packets,
          [p.id]: { ...existing, preview: p.preview, title: p.title },
        },
      };
    }
    return { packets: { ...s.packets, [p.id]: p } };
  }),

  pin: (id) => set((s) => {
    const cur = s.packets[id];
    if (!cur) return s;
    return { packets: { ...s.packets, [id]: { ...cur, pinned: !cur.pinned } } };
  }),

  remove: (id) => set((s) => {
    const { [id]: _, ...rest } = s.packets;
    return { packets: rest };
  }),

  clearUnpinned: () => set((s) => {
    const next: Record<string, PacketCardState> = {};
    for (const k of Object.keys(s.packets)) {
      if (s.packets[k].pinned) next[k] = s.packets[k];
    }
    return { packets: next };
  }),

  removeAll: () => set({ packets: {} }),

  reset: () => set({ packets: {} }),

  toggleVisible: () => set((s) => ({ visible: !s.visible })),
  hide: () => set({ visible: false }),
  show: () => set({ visible: true }),
}));
