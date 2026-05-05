import { create } from 'zustand';

export type WindowKind = 'models' | 'agents' | 'sessions' | 'node-detail' | 'outputs';

export interface WindowState {
  id: string;
  kind: WindowKind;
  title: string;
  payload?: Record<string, any>;
  position: { x: number; y: number };
  size: { w: number; h: number };
  z: number;
}

interface WindowStore {
  windows: Record<string, WindowState>;
  zSeq: number;
  spawnSeq: number;
  open: (kind: WindowKind, payload?: Record<string, any>) => void;
  toggle: (kind: WindowKind, payload?: Record<string, any>) => void;
  close: (id: string) => void;
  closeAll: () => void;
  focus: (id: string) => void;
  setPosition: (id: string, pos: { x: number; y: number }) => void;
  setSize: (id: string, size: { w: number; h: number }) => void;
  topId: () => string | null;
}

const DEFAULT_SIZE: Record<WindowKind, { w: number; h: number }> = {
  models: { w: 540, h: 600 },
  agents: { w: 480, h: 580 },
  sessions: { w: 400, h: 540 },
  'node-detail': { w: 480, h: 620 },
  outputs: { w: 560, h: 640 },
};

const TITLES: Record<WindowKind, string> = {
  models: '模型',
  agents: '部门',
  sessions: '会话',
  'node-detail': '节点详情',
  outputs: '产物文件夹',
};

function buildId(kind: WindowKind, payload?: Record<string, any>): string {
  if (kind === 'node-detail') return `node-detail:${payload?.nodeId || 'unknown'}`;
  return kind;
}

function spawnPosition(seq: number, size: { w: number; h: number }): { x: number; y: number } {
  // 中心略偏上，每开一窗向右下偏移 32px
  const baseX = Math.max(120, (window.innerWidth - size.w) / 2 - 80);
  const baseY = Math.max(80, (window.innerHeight - size.h) / 2 - 60);
  const offset = (seq % 8) * 28;
  return { x: baseX + offset, y: baseY + offset };
}

export const useWindowStore = create<WindowStore>((set, get) => ({
  windows: {},
  zSeq: 10,
  spawnSeq: 0,

  open: (kind, payload) => {
    const id = buildId(kind, payload);
    const existing = get().windows[id];
    if (existing) {
      get().focus(id);
      return;
    }
    const size = DEFAULT_SIZE[kind];
    const z = get().zSeq + 1;
    const seq = get().spawnSeq;
    set((s) => ({
      zSeq: z,
      spawnSeq: seq + 1,
      windows: {
        ...s.windows,
        [id]: {
          id,
          kind,
          title: kind === 'node-detail' ? `节点 · ${payload?.title || payload?.nodeId}` : TITLES[kind],
          payload,
          position: spawnPosition(seq, size),
          size,
          z,
        },
      },
    }));
  },

  toggle: (kind, payload) => {
    const id = buildId(kind, payload);
    if (get().windows[id]) {
      get().close(id);
    } else {
      get().open(kind, payload);
    }
  },

  close: (id) => set((s) => {
    const { [id]: _, ...rest } = s.windows;
    return { windows: rest };
  }),

  closeAll: () => set({ windows: {} }),

  focus: (id) => {
    const cur = get().windows[id];
    if (!cur) return;
    const z = get().zSeq + 1;
    set((s) => ({
      zSeq: z,
      windows: { ...s.windows, [id]: { ...cur, z } },
    }));
  },

  setPosition: (id, position) => {
    const cur = get().windows[id];
    if (!cur) return;
    set((s) => ({ windows: { ...s.windows, [id]: { ...cur, position } } }));
  },

  setSize: (id, size) => {
    const cur = get().windows[id];
    if (!cur) return;
    set((s) => ({ windows: { ...s.windows, [id]: { ...cur, size } } }));
  },

  topId: () => {
    const ws = Object.values(get().windows);
    if (ws.length === 0) return null;
    return ws.reduce((a, b) => (a.z > b.z ? a : b)).id;
  },
}));
