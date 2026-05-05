// 监听 graph.edges 变化 → 推导出 PacketCard 事件 → upsert 到 packetStore。
// 卡片 id 直接用 edge.id，保证幂等。

import { useEffect } from 'react';
import { useSessionStore, selectActiveGraph } from '@/store/sessionStore';
import { usePacketStore } from './usePacketStore';
import { edgeTypeToPacketKind, PACKET_KIND_LABEL, type PacketCardState } from './packetTypes';
import type { RunGraph, RunNode } from '@/adapter/runGraph';

function previewFor(kind: ReturnType<typeof edgeTypeToPacketKind>, source?: RunNode, target?: RunNode): string {
  if (!kind) return '';
  if (kind === 'task_packet' && target?.taskPacket) {
    const p = target.taskPacket;
    return `指令：${[p.objective, p.task].filter(Boolean).join(' · ')}`.slice(0, 140);
  }
  if (kind === 'worker_output') {
    return `结果：${source?.latestOutput || ''}`.slice(0, 140);
  }
  if (kind === 'validation' && source?.validation) {
    const v = source.validation;
    return `质检：${v.pass_gate} · ${v.summary || ''}`.slice(0, 140);
  }
  if (kind === 'rework' && source?.validation?.rework_targets?.length) {
    return `返工：${source.validation.rework_targets[0].summary}`.slice(0, 140);
  }
  if (kind === 'finalize') {
    return `交付：${target?.latestOutput || '汇总中…'}`.slice(0, 140);
  }
  return '';
}

export function usePacketEvents() {
  const graph = useSessionStore(selectActiveGraph);
  const upsert = usePacketStore((s) => s.upsert);
  const reset = usePacketStore((s) => s.reset);

  // graph 切换会话或重启 run 时清空
  const runId = graph.runId;
  useEffect(() => { reset(); }, [runId, reset]);

  useEffect(() => {
    deriveAndUpsert(graph, upsert);
  }, [graph.edges, graph.nodes, upsert]);
}

function deriveAndUpsert(graph: RunGraph, upsert: (p: PacketCardState) => void) {
  for (const edge of Object.values(graph.edges)) {
    const kind = edgeTypeToPacketKind(edge.type);
    if (!kind) continue;
    const source = graph.nodes[edge.source];
    const target = graph.nodes[edge.target];
    if (!source || !target) continue;
    const sourceAgentId = source.agentId || source.type;
    const targetAgentId = target.agentId || target.type;
    upsert({
      id: edge.id,
      kind,
      sourceAgentId,
      targetAgentId,
      title: `${PACKET_KIND_LABEL[kind]} · ${sourceAgentId} → ${targetAgentId}`,
      preview: previewFor(kind, source, target),
      createdAt: Date.now(),
      pinned: false,
      detailNodeId: kind === 'task_packet' || kind === 'rework' ? target.id : source.id,
    });
  }
}
