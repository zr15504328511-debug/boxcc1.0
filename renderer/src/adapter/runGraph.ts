// RunGraph schema — UI 只消费这个结构。
// graphAdapter 负责把后端事件流推导成 RunGraph。

export type NodeType = 'user' | 'orc' | 'worker' | 'critic' | 'artifact';

export type RunNodeStatus =
  | 'idle'
  | 'running'
  | 'completed'
  | 'failed'
  | 'needs_rework'
  | 'reworking'
  | 'validated'
  | 'timed_out';

export interface WorkerTaskPacket {
  objective?: string;
  task?: string;
  context?: string[];
  constraints?: string[];
  required_output?: string[];
  requested_skill_packs?: string[];
  priority?: 'low' | 'normal' | 'high';
  notes?: string[];
  success_criteria?: string[];
}

export interface ValidationFinding {
  owner: string;
  summary: string;
}

export interface ValidationReport {
  pass_gate: 'passed' | 'fixes_required' | 'failed' | 'unknown';
  summary?: string;
  rework_targets?: ValidationFinding[];
  raw_text?: string;
  created_at?: string;
}

export interface StreamLogEntry {
  ts: number;
  status?: RunNodeStatus | 'pending';
  title?: string;
  summary?: string;
}

export interface RunNode {
  id: string;
  type: NodeType;
  agentId?: string;
  title: string;
  status: RunNodeStatus;
  taskPacket?: WorkerTaskPacket;
  streamLog: StreamLogEntry[];
  latestOutput?: string;
  validation?: ValidationReport;
  artifact?: { kind: string; content: string } | null;
  errorMessage?: string;
  position?: { x: number; y: number };
  collapsed?: boolean;
  meta?: Record<string, any>;
}

export type EdgeType =
  | 'user_to_orc'
  | 'task_packet'
  | 'worker_output'
  | 'validation'
  | 'rework'
  | 'finalize';

export interface RunEdge {
  id: string;
  source: string;
  target: string;
  type: EdgeType;
  status: 'pending' | 'active' | 'done' | 'failed';
  label?: string;
}

export interface RunGraph {
  runId: string | null;
  nodes: Record<string, RunNode>;
  edges: Record<string, RunEdge>;
  startedAt: number | null;
  finishedAt: number | null;
  finalAnswer?: string;
  status: 'idle' | 'running' | 'completed' | 'failed';
}

export const emptyRunGraph = (): RunGraph => ({
  runId: null,
  nodes: {},
  edges: {},
  startedAt: null,
  finishedAt: null,
  status: 'idle',
});

export const nodeIdFor = {
  user: () => 'user',
  orc: () => 'orc',
  worker: (agentId: string) => `worker:${agentId}`,
  critic: (agentId = 'crt') => `critic:${agentId}`,
  final: () => 'final',
};
