// 书签间扫光层 — 监听 graph.edges，当出现新的 active edge 时
// 在 BookmarkStrip 容器内沿色条释放一颗光球，从 source 书签滑到 target 书签。
// 扫光颜色取 source agent 的颜色。完全不影响中央桌面。

import { useEffect, useRef, useState } from 'react';
import { useSessionStore, selectActiveGraph } from '@/store/sessionStore';
import { colorForAgent } from '@/theme/tokens';
import type { RunGraph } from '@/adapter/runGraph';

interface SweepInstance {
  id: string;          // edge.id + ':' + serial 防重复
  fromY: number;
  toY: number;
  color: string;
  duration: number;
}

const BOOKMARK_H = 58;
const BOOKMARK_GAP = 8;
const STRIPE_PER = BOOKMARK_H + BOOKMARK_GAP;

function nodeAgentId(graph: RunGraph, nodeId: string): string | undefined {
  return graph.nodes[nodeId]?.agentId || graph.nodes[nodeId]?.type;
}

interface Props {
  rosterAgentIds: string[];   // 当前 strip 渲染顺序里的 agentId 列表（顺序 = 渲染顺序）
}

export function SweepEffectLayer({ rosterAgentIds }: Props) {
  const graph = useSessionStore(selectActiveGraph);
  const colors = useSessionStore((s) => s.bookmarkColors);

  const [sweeps, setSweeps] = useState<SweepInstance[]>([]);
  const seenEdgeRef = useRef<Set<string>>(new Set());
  const serialRef = useRef(0);

  // run 切换 / 重启时清空 seen
  const runId = graph.runId;
  useEffect(() => {
    seenEdgeRef.current.clear();
    setSweeps([]);
  }, [runId]);

  useEffect(() => {
    // 每个 edge 在第一次出现 active 时触发一次扫光
    const newSweeps: SweepInstance[] = [];
    for (const edge of Object.values(graph.edges)) {
      if (edge.status !== 'active' && edge.status !== 'done' && edge.status !== 'failed') continue;
      // user_to_orc 不需要（user 是浅灰，没意义）
      if (edge.type === 'user_to_orc') continue;
      if (seenEdgeRef.current.has(edge.id)) continue;
      seenEdgeRef.current.add(edge.id);

      const sourceAgent = nodeAgentId(graph, edge.source) || 'orc';
      const targetAgent = nodeAgentId(graph, edge.target) || '';

      const sourceIdx = rosterAgentIds.indexOf(sourceAgent);
      const targetIdx = rosterAgentIds.indexOf(targetAgent);
      if (sourceIdx < 0 || targetIdx < 0) continue;

      const fromY = sourceIdx * STRIPE_PER + BOOKMARK_H / 2 - 6;
      const toY = targetIdx * STRIPE_PER + BOOKMARK_H / 2 - 6;
      const distance = Math.abs(targetIdx - sourceIdx);
      const duration = Math.max(450, Math.min(1100, 280 + distance * 110));

      newSweeps.push({
        id: `${edge.id}:${++serialRef.current}`,
        fromY,
        toY,
        color: colorForAgent(sourceAgent, colors),
        duration,
      });
    }
    if (newSweeps.length > 0) {
      setSweeps((prev) => [...prev, ...newSweeps]);
      // 动画结束自动清理
      for (const s of newSweeps) {
        setTimeout(() => {
          setSweeps((prev) => prev.filter((x) => x.id !== s.id));
        }, s.duration + 60);
      }
    }
  }, [graph.edges, graph.nodes, rosterAgentIds, colors]);

  return (
    <div
      className="absolute pointer-events-none"
      style={{ left: 0, top: 0, right: 0, bottom: 0, zIndex: 250 }}
      aria-hidden
    >
      {sweeps.map((s) => (
        <div
          key={s.id}
          className="bookmark-sweep bookmark-sweep--anim"
          style={{
            color: s.color,
            ['--from-y' as any]: `${s.fromY}px`,
            ['--to-y' as any]: `${s.toY}px`,
            ['--sweep-dur' as any]: `${s.duration}ms`,
          }}
        />
      ))}
    </div>
  );
}
