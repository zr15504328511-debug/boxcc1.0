// 设计令牌 — 桌面 OS 风格。
// 颜色取自 macOS Sonoma 暗模式 + Linear 夜间饱和度。

export const tokens = {
  color: {
    // 桌面背景渐变
    desktop: {
      from: '#0a0d12',
      mid: '#13182a',
      to: '#0a0d12',
      glowA: 'rgba(124,156,255,0.10)',
      glowB: 'rgba(218,108,232,0.07)',
      glowC: 'rgba(90,209,196,0.06)',
    },
    // 玻璃面板
    glass: {
      base: 'rgba(255,255,255,0.05)',
      raised: 'rgba(255,255,255,0.07)',
      stroke: 'rgba(255,255,255,0.08)',
      strokeStrong: 'rgba(255,255,255,0.16)',
      highlight: 'rgba(255,255,255,0.04)',
      shadow: 'rgba(0,0,0,0.45)',
    },
    // 文本
    text: {
      strong: '#f3f5f8',
      base: '#dde3ec',
      dim: '#9aa6b6',
      faint: '#5d6678',
    },
    // 状态
    status: {
      idle: '#5d6678',
      running: '#7c9cff',
      runningGlow: 'rgba(124,156,255,0.45)',
      completed: '#5dd29b',
      failed: '#ef6b6b',
      warn: '#f0b341',
    },
    // agent 配色（左色条 / 头像底色）
    agent: {
      orc: '#7c9cff',
      dom: '#5ad1c4',
      pln: '#f0b341',
      ana: '#c39bff',
      cpy: '#ff8aae',
      crt: '#f0b341',
      user: '#9aa6b6',
      artifact: '#5dd29b',
    },
  },
  radius: {
    icon: 18,
    window: 14,
    card: 12,
    chip: 6,
  },
  shadow: {
    iconHover: '0 8px 24px rgba(0,0,0,0.45), 0 0 0 1px rgba(255,255,255,0.08) inset',
    window: '0 30px 60px -20px rgba(0,0,0,0.7), 0 0 0 1px rgba(255,255,255,0.10) inset, 0 1px 0 rgba(255,255,255,0.05) inset',
    windowFocused: '0 40px 80px -20px rgba(0,0,0,0.85), 0 0 0 1px rgba(124,156,255,0.30), 0 1px 0 rgba(255,255,255,0.08) inset',
    composer: '0 18px 40px -12px rgba(0,0,0,0.6), 0 0 0 1px rgba(255,255,255,0.10) inset',
    nodeIdle: '0 4px 14px rgba(0,0,0,0.35), 0 0 0 1px rgba(255,255,255,0.06) inset',
    nodeRunning: '0 6px 22px rgba(124,156,255,0.18), 0 0 0 1px rgba(124,156,255,0.30) inset',
  },
  blur: {
    window: 'blur(28px) saturate(180%)',
    composer: 'blur(22px) saturate(180%)',
    icon: 'blur(14px) saturate(170%)',
    node: 'blur(12px) saturate(160%)',
  },
};

export const agentColor = (id?: string): string => {
  return (tokens.color.agent as Record<string, string>)[id || ''] || tokens.color.text.dim;
};

// 书签调色盘 — 8 个精选色，色相均匀分布，饱和度统一
export const BOOKMARK_PALETTE: { id: string; name: string; hex: string }[] = [
  { id: 'indigo',   name: '靛蓝', hex: '#7c9cff' },
  { id: 'teal',     name: '青绿', hex: '#5ad1c4' },
  { id: 'amber',    name: '琥珀', hex: '#f0b341' },
  { id: 'violet',   name: '紫罗', hex: '#c39bff' },
  { id: 'rose',     name: '玫红', hex: '#ff8aae' },
  { id: 'coral',    name: '珊瑚', hex: '#ff8c69' },
  { id: 'lime',     name: '青柠', hex: '#a3e068' },
  { id: 'lavender', name: '薰衣', hex: '#b6a3ff' },
];

// 默认每个 agent 的预设色
export const DEFAULT_BOOKMARK_COLORS: Record<string, string> = {
  user: '#9aa6b6',
  orc: '#7c9cff',
  dom: '#5ad1c4',
  pln: '#f0b341',
  ana: '#c39bff',
  cpy: '#ff8aae',
  crt: '#ff8c69',
  artifact: '#a3e068',
};

function hashIndex(s: string, n: number): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h << 5) - h + s.charCodeAt(i);
  return Math.abs(h) % n;
}

/**
 * 取 agent 的颜色：用户自定义 → 预设 → palette hash fallback。
 */
export function colorForAgent(
  agentId: string,
  customColors: Record<string, string>,
): string {
  if (customColors[agentId]) return customColors[agentId];
  if (DEFAULT_BOOKMARK_COLORS[agentId]) return DEFAULT_BOOKMARK_COLORS[agentId];
  return BOOKMARK_PALETTE[hashIndex(agentId, BOOKMARK_PALETTE.length)].hex;
}
