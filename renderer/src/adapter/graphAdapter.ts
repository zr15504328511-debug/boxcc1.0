// graphAdapter — 把后端 SSE 事件流推导为 RunGraph。
// 后端目前没有统一 graph_event，因此从 run_step / checklist_sync / answer_delta / done 派生。
//
// 后端字段约定（见 backend/runtime_events.py / backend/app/routers/chat.py）：
//   run_step:        { phase: 'orc'|'worker'|'critic'|'final', agent_id, step_id, status, title, summary, meta }
//   checklist_sync:  { selected_workers, checklist[] }
//   node_task_packet:{ node_id, agent_id, task_packet, available_skill_packs, is_rework }
//   node_output_*:   { node_id, agent_id, delta/content, status, error }
//   answer_delta:    { delta }
//   done:            { message, department_results[], workflow_artifact, checklist }
//   error:           { error }

import type { StreamEvent } from '@/types/boxccApi';
import {
  emptyRunGraph,
  nodeIdFor,
  type RunGraph,
  type RunNode,
  type RunNodeStatus,
  type RunEdge,
  type WorkerTaskPacket,
  type ValidationReport,
} from './runGraph';

const NON_WORKER_AGENT_IDS = new Set(['orc', 'crt', 'artifact', 'final', 'user']);

function isWorkerAgentId(agentId: string | undefined): agentId is string {
  return !!agentId && !NON_WORKER_AGENT_IDS.has(agentId);
}

function ensureNode(graph: RunGraph, node: RunNode) {
  if (!graph.nodes[node.id]) {
    graph.nodes[node.id] = node;
  }
}

function ensureEdge(graph: RunGraph, edge: RunEdge) {
  if (!graph.edges[edge.id]) {
    graph.edges[edge.id] = edge;
  }
}

function setNode(graph: RunGraph, id: string, patch: Partial<RunNode>) {
  const existing = graph.nodes[id];
  if (!existing) return;
  graph.nodes[id] = { ...existing, ...patch };
}

function setEdge(graph: RunGraph, id: string, patch: Partial<RunEdge>) {
  const existing = graph.edges[id];
  if (!existing) return;
  graph.edges[id] = { ...existing, ...patch };
}

function statusFromEventStatus(s?: string): RunNodeStatus {
  if (s === 'running') return 'running';
  if (s === 'completed') return 'completed';
  if (s === 'failed') return 'failed';
  if (s === 'timed_out') return 'timed_out';
  if (s === 'reworking') return 'reworking';
  if (s === 'needs_rework') return 'needs_rework';
  if (s === 'validated') return 'validated';
  if (s === 'pending') return 'idle';
  return 'idle';
}

function appendStreamLog(graph: RunGraph, nodeId: string, ev: StreamEvent) {
  const n = graph.nodes[nodeId];
  if (!n) return;
  const stepId = ev.step_id || '';
  const isRework = Boolean(ev.is_rework || ev.meta?.is_rework || stepId.toLowerCase().includes('rework'));
  n.streamLog = [
    ...n.streamLog,
    {
      ts: Date.now(),
      status: statusFromEventStatus(ev.status),
      title: ev.title,
      summary: ev.summary,
      eventType: ev.type,
      stepId,
      phase: ev.phase,
      agentId: ev.agent_id,
      isRework,
      passGate: typeof ev.meta?.pass_gate === 'string' ? ev.meta.pass_gate : undefined,
      reviewRound: typeof ev.meta?.review_round === 'number' ? ev.meta.review_round : undefined,
    },
  ];
}

/**
 * 初始化一次新的运行：用户消息进入，立即创建 user 节点和 orc 节点。
 */
export function startRun(graph: RunGraph, opts: { runId: string; userText: string }): RunGraph {
  const next = emptyRunGraph();
  next.runId = opts.runId;
  next.startedAt = Date.now();
  next.status = 'running';

  const userId = nodeIdFor.user();
  const orcId = nodeIdFor.orc();

  next.nodes[userId] = {
    id: userId,
    type: 'user',
    title: '用户任务',
    status: 'completed',
    streamLog: [],
    latestOutput: opts.userText,
  };
  next.nodes[orcId] = {
    id: orcId,
    type: 'orc',
    agentId: 'orc',
    title: '主席团 · orc',
    status: 'idle',
    streamLog: [],
  };
  next.edges[`${userId}->${orcId}`] = {
    id: `${userId}->${orcId}`,
    source: userId,
    target: orcId,
    type: 'user_to_orc',
    status: 'active',
  };
  return next;
}

/**
 * 应用一个流式事件到当前图。返回新图（不可变更新）。
 */
export function applyEvent(prev: RunGraph, ev: StreamEvent): RunGraph {
  // shallow clone — 上层用 zustand 替换整个图
  const graph: RunGraph = {
    ...prev,
    nodes: { ...prev.nodes },
    edges: { ...prev.edges },
  };

  switch (ev.type) {
    case 'run_step':
      return handleRunStep(graph, ev);
    case 'checklist_sync':
      return handleChecklistSync(graph, ev);
    case 'node_task_packet':
      return handleNodeTaskPacket(graph, ev);
    case 'node_output_delta':
      return handleNodeOutputDelta(graph, ev);
    case 'node_output_done':
      return handleNodeOutputDone(graph, ev);
    case 'answer_delta':
      return handleAnswerDelta(graph, ev);
    case 'done':
      return handleDone(graph, ev);
    case 'error':
      return handleError(graph, ev);
    default:
      return graph;
  }
}

function normalizeEventNodeId(ev: StreamEvent): string | null {
  if (ev.node_id === 'final:answer') return nodeIdFor.final();
  if (ev.node_id) return ev.node_id;
  if (ev.phase === 'worker' && ev.agent_id) return nodeIdFor.worker(ev.agent_id);
  if (ev.phase === 'critic') return nodeIdFor.critic(ev.agent_id || 'crt');
  if (ev.phase === 'final') return nodeIdFor.final();
  if (ev.agent_id === 'orc') return nodeIdFor.orc();
  return null;
}

function ensureEventNode(graph: RunGraph, ev: StreamEvent): string | null {
  const nodeId = normalizeEventNodeId(ev);
  if (!nodeId) return null;
  if (graph.nodes[nodeId]) return nodeId;

  if (nodeId.startsWith('worker:')) {
    const agentId = ev.agent_id || nodeId.slice('worker:'.length);
    graph.nodes[nodeId] = {
      id: nodeId,
      type: 'worker',
      agentId,
      title: workerDisplayName(agentId),
      status: 'idle',
      streamLog: [],
    };
    const orcId = nodeIdFor.orc();
    if (graph.nodes[orcId]) {
      ensureEdge(graph, {
        id: `${orcId}->${nodeId}`,
        source: orcId,
        target: nodeId,
        type: 'task_packet',
        status: 'active',
        label: '任务包',
      });
    }
    return nodeId;
  }

  if (nodeId.startsWith('critic:')) {
    const agentId = ev.agent_id || 'crt';
    graph.nodes[nodeId] = {
      id: nodeId,
      type: 'critic',
      agentId,
      title: workerDisplayName(agentId),
      status: 'idle',
      streamLog: [],
    };
    for (const wid of Object.keys(graph.nodes)) {
      if (graph.nodes[wid].type !== 'worker') continue;
      ensureEdge(graph, {
        id: `${wid}->${nodeId}`,
        source: wid,
        target: nodeId,
        type: 'worker_output',
        status: 'active',
        label: '输出送审',
      });
    }
    return nodeId;
  }

  if (nodeId === nodeIdFor.final()) {
    graph.nodes[nodeId] = {
      id: nodeId,
      type: 'artifact',
      title: '最终交付',
      status: 'running',
      streamLog: [],
      latestOutput: '',
    };
    return nodeId;
  }

  return nodeId;
}

function handleNodeTaskPacket(graph: RunGraph, ev: StreamEvent): RunGraph {
  const nodeId = ensureEventNode(graph, ev);
  if (!nodeId || graph.nodes[nodeId].type === 'artifact') return graph;
  setNode(graph, nodeId, {
    status: statusFromEventStatus(ev.status),
    taskPacket: ev.task_packet as WorkerTaskPacket | undefined,
    meta: {
      ...(graph.nodes[nodeId].meta || {}),
      available_skill_packs: ev.available_skill_packs || [],
      is_rework: Boolean(ev.is_rework),
    },
  });
  return graph;
}

function handleNodeOutputDelta(graph: RunGraph, ev: StreamEvent): RunGraph {
  const nodeId = ensureEventNode(graph, ev);
  if (!nodeId || nodeId === nodeIdFor.final()) return graph;
  const node = graph.nodes[nodeId];
  setNode(graph, nodeId, {
    status: node.status === 'idle' ? 'running' : node.status,
    latestOutput: (node.latestOutput || '') + (ev.delta || ''),
  });
  return graph;
}

function handleNodeOutputDone(graph: RunGraph, ev: StreamEvent): RunGraph {
  const nodeId = ensureEventNode(graph, ev);
  if (!nodeId || nodeId === nodeIdFor.final()) return graph;
  const status = statusFromEventStatus(ev.status);
  setNode(graph, nodeId, {
    status,
    latestOutput: ev.content || graph.nodes[nodeId].latestOutput,
    errorMessage: ev.error,
  });
  for (const eid of Object.keys(graph.edges)) {
    const edge = graph.edges[eid];
    if ((edge.source === nodeId || edge.target === nodeId) && edge.status === 'active') {
      setEdge(graph, eid, { status: status === 'failed' || status === 'timed_out' ? 'failed' : 'done' });
    }
  }
  return graph;
}

function handleRunStep(graph: RunGraph, ev: StreamEvent): RunGraph {
  const phase = ev.phase;
  const agentId = ev.agent_id;
  const stepId = ev.step_id || '';

  // ORC 阶段
  if (phase === 'orc') {
    const orcId = nodeIdFor.orc();
    if (!graph.nodes[orcId]) {
      graph.nodes[orcId] = {
        id: orcId,
        type: 'orc',
        agentId: 'orc',
        title: '主席团 · orc',
        status: 'idle',
        streamLog: [],
      };
    }
    setNode(graph, orcId, { status: statusFromEventStatus(ev.status) });
    appendStreamLog(graph, orcId, ev);

    // orc 选中 worker 列表 → 创建 worker 节点 + task_packet 边
    const selected = (ev.meta?.selected_workers as string[] | undefined)
      || (ev.meta?.workers as string[] | undefined)
      || [];
    if (selected.length > 0) {
      for (const wid of selected) {
        const nid = nodeIdFor.worker(wid);
        if (!graph.nodes[nid]) {
          graph.nodes[nid] = {
            id: nid,
            type: 'worker',
            agentId: wid,
            title: workerDisplayName(wid),
            status: 'idle',
            streamLog: [],
          };
        }
        const eid = `${orcId}->${nid}`;
        if (!graph.edges[eid]) {
          graph.edges[eid] = {
            id: eid,
            source: orcId,
            target: nid,
            type: 'task_packet',
            status: 'active',
            label: '任务包',
          };
        }
      }
    }
    return graph;
  }

  // Worker 阶段
  if (phase === 'worker' && isWorkerAgentId(agentId)) {
    const nid = nodeIdFor.worker(agentId);
    if (!graph.nodes[nid]) {
      graph.nodes[nid] = {
        id: nid,
        type: 'worker',
        agentId,
        title: workerDisplayName(agentId),
        status: 'idle',
        streamLog: [],
      };
      // 兜底：如果 orc 没显式发选中事件，但 worker 节点冒出来了，自动建边
      const orcId = nodeIdFor.orc();
      if (graph.nodes[orcId]) {
        const eid = `${orcId}->${nid}`;
        if (!graph.edges[eid]) {
          graph.edges[eid] = {
            id: eid,
            source: orcId,
            target: nid,
            type: 'task_packet',
            status: 'active',
            label: '任务包',
          };
        }
      }
    }
    setNode(graph, nid, { status: statusFromEventStatus(ev.status) });
    appendStreamLog(graph, nid, ev);

    // 把 task_packet 从 meta 里捞出来（如果后端塞了）
    const packet = (ev.meta?.task_packet as WorkerTaskPacket | undefined);
    if (packet) {
      setNode(graph, nid, { taskPacket: packet });
    }

    // 完成时，把 task_packet 边从 active 改成 done，并加 worker_output 边到未来 critic / final
    if (ev.status === 'completed' || ev.status === 'failed') {
      const orcId = nodeIdFor.orc();
      const eid = `${orcId}->${nid}`;
      if (graph.edges[eid]) {
        setEdge(graph, eid, { status: ev.status === 'failed' ? 'failed' : 'done' });
      }
    }
    return graph;
  }

  // Critic 阶段
  if (phase === 'critic') {
    const cid = nodeIdFor.critic(agentId || 'crt');
    if (!graph.nodes[cid]) {
      graph.nodes[cid] = {
        id: cid,
        type: 'critic',
        agentId: agentId || 'crt',
        title: '质检部 · crt',
        status: 'idle',
        streamLog: [],
      };
      // 从所有已存在的 worker 节点连 validation 边到 critic
      for (const wid of Object.keys(graph.nodes)) {
        if (graph.nodes[wid].type !== 'worker') continue;
        const eid = `${wid}->${cid}`;
        if (!graph.edges[eid]) {
          graph.edges[eid] = {
            id: eid,
            source: wid,
            target: cid,
            type: 'worker_output',
            status: 'active',
            label: '输出送审',
          };
        }
      }
    }
    setNode(graph, cid, { status: statusFromEventStatus(ev.status) });
    appendStreamLog(graph, cid, ev);
    return graph;
  }

  // Final 阶段：单纯标记进入 final，节点会在 done 里物化
  if (phase === 'final') {
    const orcId = nodeIdFor.orc();
    setNode(graph, orcId, { status: ev.status === 'completed' ? 'completed' : 'running' });
    appendStreamLog(graph, orcId, ev);
    return graph;
  }

  return graph;
}

function handleChecklistSync(graph: RunGraph, ev: StreamEvent): RunGraph {
  // 提前把 selected_workers 物化（有的运行会先发 checklist_sync 再发 orc selected）
  const selected = ev.selected_workers || [];
  for (const wid of selected) {
    if (!isWorkerAgentId(wid)) continue;
    const nid = nodeIdFor.worker(wid);
    if (!graph.nodes[nid]) {
      graph.nodes[nid] = {
        id: nid,
        type: 'worker',
        agentId: wid,
        title: workerDisplayName(wid),
        status: 'idle',
        streamLog: [],
      };
      const orcId = nodeIdFor.orc();
      if (graph.nodes[orcId]) {
        const eid = `${orcId}->${nid}`;
        if (!graph.edges[eid]) {
          graph.edges[eid] = {
            id: eid,
            source: orcId,
            target: nid,
            type: 'task_packet',
            status: 'active',
            label: '任务包',
          };
        }
      }
    }
  }

  // 把 checklist 项绑到对应 worker（仅作为 meta 辅助）
  if (Array.isArray(ev.checklist)) {
    const byOwner = new Map<string, any[]>();
    for (const item of ev.checklist) {
      const owner = item?.owner;
      if (!owner) continue;
      if (!byOwner.has(owner)) byOwner.set(owner, []);
      byOwner.get(owner)!.push(item);
    }
    for (const [owner, items] of byOwner.entries()) {
      const nid = nodeIdFor.worker(owner);
      if (graph.nodes[nid]) {
        setNode(graph, nid, {
          meta: { ...(graph.nodes[nid].meta || {}), checklist: items },
        });
      }
    }
  }

  return graph;
}

function handleAnswerDelta(graph: RunGraph, ev: StreamEvent): RunGraph {
  // answer_delta 是最终汇总文本流，绑到 final 节点（如果还没就先放在 orc 上）
  const finalId = nodeIdFor.final();
  if (!graph.nodes[finalId]) {
    graph.nodes[finalId] = {
      id: finalId,
      type: 'artifact',
      title: '最终交付',
      status: 'running',
      streamLog: [],
      latestOutput: '',
    };
    // 优先从 critic 连过去；没有 critic 则从 orc
    const criticId = Object.keys(graph.nodes).find((k) => graph.nodes[k].type === 'critic');
    const fromId = criticId || nodeIdFor.orc();
    if (graph.nodes[fromId]) {
      const eid = `${fromId}->${finalId}`;
      if (!graph.edges[eid]) {
        graph.edges[eid] = {
          id: eid,
          source: fromId,
          target: finalId,
          type: 'finalize',
          status: 'active',
          label: '汇总',
        };
      }
    }
  }
  const cur = graph.nodes[finalId];
  graph.nodes[finalId] = {
    ...cur,
    latestOutput: (cur.latestOutput || '') + (ev.delta || ''),
  };
  return graph;
}

function handleDone(graph: RunGraph, ev: StreamEvent): RunGraph {
  // 1. 物化最终节点（如果 answer_delta 没创建过）
  const finalId = nodeIdFor.final();
  if (!graph.nodes[finalId]) {
    graph.nodes[finalId] = {
      id: finalId,
      type: 'artifact',
      title: '最终交付',
      status: 'completed',
      streamLog: [],
      latestOutput: ev.message?.content || '',
    };
    const criticId = Object.keys(graph.nodes).find((k) => graph.nodes[k].type === 'critic');
    const fromId = criticId || nodeIdFor.orc();
    if (graph.nodes[fromId]) {
      const eid = `${fromId}->${finalId}`;
      if (!graph.edges[eid]) {
        graph.edges[eid] = {
          id: eid,
          source: fromId,
          target: finalId,
          type: 'finalize',
          status: 'done',
          label: '汇总',
        };
      } else {
        setEdge(graph, eid, { status: 'done' });
      }
    }
  } else {
    setNode(graph, finalId, {
      status: 'completed',
      latestOutput: graph.nodes[finalId].latestOutput || ev.message?.content || '',
      artifact: ev.workflow_artifact
        ? { kind: 'workflow', content: JSON.stringify(ev.workflow_artifact, null, 2) }
        : null,
    });
  }

  // 2. 回填每个 worker 的 latestOutput 和 task_packet
  if (Array.isArray(ev.department_results)) {
    for (const dept of ev.department_results) {
      if (!dept) continue;
      const aid = dept.agent_id || '';
      if (!aid) continue;
      const nid = nodeIdFor.worker(aid);
      const node = graph.nodes[nid];
      if (!node) continue;
      const newStatus: RunNodeStatus = dept.error ? 'failed' : (node.status === 'idle' ? 'completed' : node.status);
      setNode(graph, nid, {
        latestOutput: dept.content || node.latestOutput,
        taskPacket: dept.task_packet || node.taskPacket,
        errorMessage: dept.error,
        status: newStatus,
      });
    }
  }

  // 3. 标记所有"还在 active"的边为 done
  for (const eid of Object.keys(graph.edges)) {
    if (graph.edges[eid].status === 'active') {
      setEdge(graph, eid, { status: 'done' });
    }
  }

  // 4. 收尾
  graph.finishedAt = Date.now();
  graph.status = 'completed';
  graph.finalAnswer = graph.nodes[finalId]?.latestOutput;

  return graph;
}

function handleError(graph: RunGraph, ev: StreamEvent): RunGraph {
  // 把所有 running 节点切换到 failed，并标记一条失败边
  for (const id of Object.keys(graph.nodes)) {
    if (graph.nodes[id].status === 'running') {
      setNode(graph, id, { status: 'failed', errorMessage: ev.error });
    }
  }
  for (const eid of Object.keys(graph.edges)) {
    if (graph.edges[eid].status === 'active') {
      setEdge(graph, eid, { status: 'failed' });
    }
  }
  graph.finishedAt = Date.now();
  graph.status = 'failed';
  return graph;
}

export function workerDisplayName(agentId: string): string {
  switch (agentId) {
    case 'dom': return '学术部 · dom';
    case 'pln': return '企划部 · pln';
    case 'ana': return '经营部 · ana';
    case 'cpy': return '宣传部 · cpy';
    case 'crt': return '质检部 · crt';
    case 'orc': return '主席团 · orc';
    default: return agentId;
  }
}

/**
 * 直答任务退化：done 时如果没有 worker / critic 节点出现，
 * 直接补一条 orc → final 的 finalize 边，并把 orc 标记为 completed。
 */
export function ensureDirectAnswerFallback(graph: RunGraph): RunGraph {
  const hasWorker = Object.values(graph.nodes).some((n) => n.type === 'worker');
  const hasCritic = Object.values(graph.nodes).some((n) => n.type === 'critic');
  if (hasWorker || hasCritic) return graph;

  const next = { ...graph, nodes: { ...graph.nodes }, edges: { ...graph.edges } };
  const orcId = nodeIdFor.orc();
  const finalId = nodeIdFor.final();
  if (next.nodes[orcId]) setNode(next, orcId, { status: 'completed' });
  if (next.nodes[orcId] && next.nodes[finalId]) {
    const eid = `${orcId}->${finalId}`;
    if (!next.edges[eid]) {
      next.edges[eid] = {
        id: eid,
        source: orcId,
        target: finalId,
        type: 'finalize',
        status: 'done',
        label: '直答',
      };
    }
  }
  return next;
}
