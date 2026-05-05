// 固定的右侧书签清单 — 顺序即从上到下排列。
// 每个条目对应一个 agent，与当前 graph 里的 RunNode 关联（如果有）。

import type { NodeType } from '@/adapter/runGraph';
import type { AgentSpec } from '@/types/boxccApi';

export interface BookmarkSpec {
  agentId: string;        // 节点 lookup key 同时也是颜色 key
  nodeIdSel: 'user' | 'orc' | `worker:${string}` | 'critic:crt' | `critic:${string}` | 'final';
  type: NodeType;
  label: string;
  shortLabel: string;     // 3-字母大写
  description: string;
}

export type RosterEntry =
  | { kind: 'agent'; spec: BookmarkSpec }
  | { kind: 'add' };

export const BASE_BOOKMARK_ROSTER: BookmarkSpec[] = [
  { agentId: 'user',     nodeIdSel: 'user',         type: 'user',     label: '用户任务',      shortLabel: '用户', description: '原始请求' },
  { agentId: 'orc',      nodeIdSel: 'orc',          type: 'orc',      label: '主席团 orc',    shortLabel: '编排', description: '路由 / 拆解' },
  { agentId: 'dom',      nodeIdSel: 'worker:dom',   type: 'worker',   label: '学术部 dom',    shortLabel: '学术', description: '面料 / 资料' },
  { agentId: 'pln',      nodeIdSel: 'worker:pln',   type: 'worker',   label: '企划部 pln',    shortLabel: '企划', description: 'SKU / 节奏' },
  { agentId: 'ana',      nodeIdSel: 'worker:ana',   type: 'worker',   label: '经营部 ana',    shortLabel: '经营', description: '定价 / 测算' },
  { agentId: 'cpy',      nodeIdSel: 'worker:cpy',   type: 'worker',   label: '宣传部 cpy',    shortLabel: '宣传', description: '文案 / 卖点' },
  { agentId: 'crt',      nodeIdSel: 'critic:crt',   type: 'critic',   label: '质检部 crt',    shortLabel: '质检', description: '审核 / 返工' },
  { agentId: 'artifact', nodeIdSel: 'final',        type: 'artifact', label: '最终交付',      shortLabel: '交付', description: '汇总产物' },
];

const BASE_IDS = new Set(BASE_BOOKMARK_ROSTER.map((b) => b.agentId));

/**
 * 把 store.agents 中不在 base 的 worker / critic 追加为额外书签。
 * 末尾追加一个 "+ 添加" 占位。
 */
export function deriveRoster(storeAgents: AgentSpec[]): RosterEntry[] {
  const entries: RosterEntry[] = BASE_BOOKMARK_ROSTER.map((spec) => ({ kind: 'agent', spec } as RosterEntry));

  const extras = (storeAgents || []).filter(
    (a) =>
      a &&
      a.id &&
      !BASE_IDS.has(a.id) &&
      (a.phase === 'worker' || a.phase === 'critic'),
  );

  for (const a of extras) {
    const isCritic = a.phase === 'critic';
    const nodeIdSel: BookmarkSpec['nodeIdSel'] = isCritic
      ? (`critic:${a.id}` as const)
      : (`worker:${a.id}` as const);
    const displayName = a.name || a.display_name || a.id;
    // 取中文显示名前 2 字（剥掉「部」「团」等后缀）；非中文则取前 2 字大写
    const cleaned = displayName.replace(/[部团室处科组院系]$/u, '').trim();
    const shortLabel = /[一-龥]/.test(cleaned)
      ? cleaned.slice(0, 2)
      : cleaned.slice(0, 2).toUpperCase();
    entries.push({
      kind: 'agent',
      spec: {
        agentId: a.id,
        nodeIdSel,
        type: isCritic ? 'critic' : 'worker',
        label: displayName,
        shortLabel,
        description: a.description || a.desc || (isCritic ? '审核' : '部门'),
      },
    });
  }

  entries.push({ kind: 'add' });
  return entries;
}
