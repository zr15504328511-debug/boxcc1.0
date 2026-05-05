// 漂浮卡片：把 graph 边演成"通信事件"。
// 每张卡代表一次 agent → agent 的信息传递。

import type { EdgeType } from '@/adapter/runGraph';

export type PacketKind =
  | 'task_packet'    // orc → worker：派发任务
  | 'worker_output'  // worker → critic：交差
  | 'validation'     // critic → orc：质检意见
  | 'rework'         // critic → worker：返工
  | 'finalize';      // orc → final：汇总

export interface PacketCardState {
  id: string;                // edge.id
  kind: PacketKind;
  sourceAgentId: string;
  targetAgentId: string;
  title: string;
  preview: string;           // 内容摘要 1-2 行
  createdAt: number;
  pinned: boolean;
  spawnPos?: { x: number; y: number };  // 起飞位置
  restPos?: { x: number; y: number };   // 悬停位置
  detailNodeId?: string;     // 点击展开时定位到哪个节点详情
}

export const PACKET_KIND_LABEL: Record<PacketKind, string> = {
  task_packet: '任务包',
  worker_output: '输出交差',
  validation: '质检意见',
  rework: '返工要求',
  finalize: '汇总',
};

export const PACKET_KIND_ICON: Record<PacketKind, string> = {
  task_packet: '📦',
  worker_output: '📤',
  validation: '🔍',
  rework: '🔁',
  finalize: '✅',
};

export function edgeTypeToPacketKind(edgeType: EdgeType): PacketKind | null {
  if (edgeType === 'task_packet') return 'task_packet';
  if (edgeType === 'worker_output') return 'worker_output';
  if (edgeType === 'validation') return 'validation';
  if (edgeType === 'rework') return 'rework';
  if (edgeType === 'finalize') return 'finalize';
  return null;  // user_to_orc 不形成漂浮卡
}
