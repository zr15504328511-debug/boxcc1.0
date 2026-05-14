import { useState, useMemo, useEffect } from 'react';
import { useSessionStore, selectActiveGraph } from '@/store/sessionStore';
import type { RunNode, StreamLogEntry } from '@/adapter/runGraph';
import { TaskPacketView } from '@/inspector/TaskPacketView';
import { CritiqueView } from '@/inspector/CritiqueView';
import { ArtifactPreview } from '@/inspector/ArtifactPreview';
import { agentColor } from '@/theme/tokens';
import { useTypewriter } from '@/graph/useTypewriter';

const TYPE_LABEL: Record<string, string> = {
  user: '用户任务',
  orc: '编排 / 主席团',
  worker: '部门 worker',
  critic: '质检 critic',
  artifact: '最终交付',
};

const TABS = [
  { id: 'decisions', label: '编排决策' },
  { id: 'packet', label: '任务指令' },
  { id: 'output', label: '部门输出' },
  { id: 'critique', label: '质检报告' },
  { id: 'artifact', label: '最终交付' },
  { id: 'log', label: '原始日志' },
] as const;

type TabId = typeof TABS[number]['id'];

function defaultTabFor(node: RunNode | undefined): TabId {
  if (!node) return 'decisions';
  if (node.type === 'critic') return 'critique';
  if (node.type === 'artifact') return 'artifact';
  if (node.type === 'user') return 'decisions';
  return 'decisions';
}

function relevantTabs(node: RunNode | undefined): TabId[] {
  if (!node) return ['decisions'];
  switch (node.type) {
    case 'user':     return ['decisions', 'log'];
    case 'orc':      return ['decisions', 'output', 'log'];
    case 'worker':   return ['decisions', 'packet', 'output', 'log'];
    case 'critic':   return ['decisions', 'critique', 'log'];
    case 'artifact': return ['decisions', 'artifact', 'log'];
    default:         return ['decisions', 'log'];
  }
}

interface Props {
  nodeId?: string;
}

export function NodeDetailFolder({ nodeId }: Props) {
  const graph = useSessionStore(selectActiveGraph);
  const node = nodeId ? graph.nodes[nodeId] : undefined;

  const tabs = relevantTabs(node);
  const [tab, setTab] = useState<TabId>(defaultTabFor(node));
  useEffect(() => { setTab(defaultTabFor(node)); }, [nodeId]); // reset when nodeId changes

  if (!node) {
    return (
      <div className="h-full flex items-center justify-center text-[12px] text-desk-faint">
        节点不存在或已被清理。
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      {/* header */}
      <div className="px-4 py-3 border-b border-white/5 flex items-start gap-3">
        <div
          className="w-9 h-9 rounded-lg flex items-center justify-center text-[11px] font-bold text-[#0b1020]"
          style={{ background: `linear-gradient(135deg, ${agentColor(node.agentId || node.type)}, ${agentColor(node.agentId || node.type)}cc)` }}
        >
          {(node.agentId || node.type).toUpperCase().slice(0, 3)}
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-[10px] uppercase tracking-wider text-desk-faint">
            {TYPE_LABEL[node.type]}
          </div>
          <div className="text-[14.5px] font-semibold text-desk-text mt-0.5">{node.title}</div>
          <div className="text-[10.5px] text-desk-faint mt-0.5">id: {node.id} · status: {node.status}</div>
        </div>
      </div>

      {/* tabs */}
      <div className="px-4 pt-2 flex items-center gap-1 border-b border-white/5">
        {TABS.filter((t) => tabs.includes(t.id)).map((t) => {
          const active = t.id === tab;
          return (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`px-2.5 py-1.5 text-[11.5px] rounded-t-md border-b-2 transition ${
                active
                  ? 'text-desk-text border-desk-accent'
                  : 'text-desk-dim border-transparent hover:text-desk-text'
              }`}
            >
              {t.label}
            </button>
          );
        })}
      </div>

      {/* body */}
      <div className="flex-1 overflow-y-auto px-5 py-4">
        {tab === 'decisions' && <DecisionsTab node={node} />}
        {tab === 'packet' && <TaskPacketView packet={node.taskPacket} />}
        {tab === 'output' && (
          <div className="text-[12.5px] leading-relaxed whitespace-pre-wrap text-desk-text/90">
            {node.latestOutput || <span className="text-desk-faint">尚无输出</span>}
          </div>
        )}
        {tab === 'critique' && <CritiqueView report={node.validation} />}
        {tab === 'artifact' && <ArtifactPreview content={node.latestOutput || ''} />}
        {tab === 'log' && <RawLogTab node={node} />}
      </div>
    </div>
  );
}

/* ====================  Decisions narrative tab  ==================== */

function fmtTime(ts: number): string {
  const d = new Date(ts);
  return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}:${d.getSeconds().toString().padStart(2, '0')}`;
}

function DecisionsTab({ node }: { node: RunNode }) {
  // Build narrative entries from streamLog, augmented with agent semantics.
  const entries = useMemo(() => {
    const items = (node.streamLog || []).map((e, i) => {
      const kicker = timelineTitleFor(node, e);
      const body = timelineBodyFor(node, e);
      return { ts: e.ts, kicker, body, idx: i };
    }).filter((item, i, arr) => {
      const prev = arr[i - 1];
      return !prev || prev.kicker !== item.kicker || prev.body !== item.body;
    });
    // 末尾插入"已完成"或"失败"心跳
    if (node.status === 'completed') {
      items.push({
        ts: items[items.length - 1]?.ts || Date.now(),
        kicker: '已完成',
        body: completionBlurb(node),
        idx: items.length,
      });
    } else if (node.status === 'failed') {
      items.push({
        ts: items[items.length - 1]?.ts || Date.now(),
        kicker: '执行失败',
        body: node.errorMessage || '未给出失败原因。',
        idx: items.length,
      });
    }
    return items;
  }, [node]);

  if (entries.length === 0) {
    return <div className="text-[12px] text-desk-faint">尚无可叙述的决策依据。等待节点运行后查看。</div>;
  }

  return (
    <div className="relative pl-4">
      {/* timeline rail */}
      <div className="absolute left-1.5 top-1 bottom-1 w-px bg-white/10" />
      <ul className="space-y-3">
        {entries.map((e, i) => (
          <DecisionItem key={i} ts={e.ts} kicker={e.kicker} body={e.body} isLast={i === entries.length - 1 && (node.status === 'running')} />
        ))}
      </ul>
    </div>
  );
}

function DecisionItem({ ts, kicker, body, isLast }: { ts: number; kicker: string; body: string; isLast: boolean }) {
  // 仅最后一条用打字机效果（如果节点还在运行）
  const { display, isTyping } = useTypewriter(isLast ? body : body, isLast ? 38 : 9999);
  return (
    <li className="relative">
      <div className="absolute -left-[14px] top-1 w-2 h-2 rounded-full bg-desk-accent shadow-[0_0_0_3px_rgba(124,156,255,0.18)]" />
      <div className="text-[10.5px] text-desk-faint font-mono">{fmtTime(ts)}</div>
      <div className="text-[12.5px] font-semibold text-desk-text mt-0.5">{kicker}</div>
      {body && (
        <div className="text-[12px] text-desk-dim leading-relaxed mt-1 whitespace-pre-wrap">
          {isLast ? display : body}
          {isLast && isTyping && <span className="tw-caret" />}
        </div>
      )}
    </li>
  );
}

function timelineTitleFor(node: RunNode, e: StreamLogEntry): string {
  const name = node.title;
  const status = e.status;
  const isRework = Boolean(e.isRework || e.stepId?.toLowerCase().includes('rework'));

  if (node.type === 'worker') {
    if (status === 'running') return isRework ? `${name}收到质检返工` : `${name}收到任务`;
    if (status === 'completed' || status === 'validated') return isRework ? `${name}提交返工结果` : `${name}提交分析结果`;
    if (status === 'reworking' || status === 'needs_rework') return `${name}等待返工处理`;
    if (status === 'failed' || status === 'timed_out') return `${name}执行异常`;
    return `${name}更新进展`;
  }

  if (node.type === 'critic') {
    const isRecheck = e.reviewRound === 2 || e.stepId?.includes('phase_2');
    const stage = isRecheck ? '复检' : '初审';
    if (status === 'running') return `质检部开始${stage}`;
    if (status === 'completed' || status === 'validated') {
      const gate = gateLabel(e.passGate);
      return gate ? `质检部给出${stage}结论：${gate}` : `质检部给出${stage}结论`;
    }
    if (status === 'needs_rework' || status === 'reworking') return '质检部要求返工';
    if (status === 'failed' || status === 'timed_out') return '质检部审核异常';
    return `质检部更新${stage}`;
  }

  if (node.type === 'orc') {
    if (e.stepId === 'orc_selected_workers' || e.summary?.includes('selected workers')) return '主席团完成部门选择';
    if (e.phase === 'final') return '主席团整合最终交付';
    if (status === 'running') return '主席团分析任务';
    if (status === 'completed') return '主席团完成编排';
    return '主席团更新决策';
  }

  switch (node.type) {
    case 'artifact': return '汇总输出';
    default:         return '事件';
  }
}

function gateLabel(gate?: string): string {
  if (gate === 'passed') return '通过';
  if (gate === 'fixes_required') return '需返工';
  if (gate === 'failed') return '不通过';
  return '';
}

function timelineBodyFor(node: RunNode, e: StreamLogEntry): string {
  if (e.summary) return e.summary;
  if (e.status) return statusBlurb(e.status, node);
  return '';
}

function statusBlurb(status: string, node: RunNode): string {
  if (status === 'running') return `${node.title} 进入执行状态。`;
  if (status === 'completed') return `${node.title} 已完成本步骤。`;
  if (status === 'reworking') return `${node.title} 正在根据质检意见修订。`;
  if (status === 'needs_rework') return `${node.title} 收到质检返工要求。`;
  if (status === 'validated') return `${node.title} 已通过质检确认。`;
  if (status === 'timed_out') return `${node.title} 执行超时。`;
  if (status === 'failed') return `${node.title} 失败。`;
  return '';
}

function completionBlurb(node: RunNode): string {
  if (node.type === 'critic' && node.validation) {
    const gate = node.validation.pass_gate;
    const cnt = node.validation.rework_targets?.length || 0;
    if (gate === 'passed') return '所有部门输出通过质检。';
    if (gate === 'fixes_required') return `通过条件性，需 ${cnt} 项修正。`;
    if (gate === 'failed') return `质检不通过：${node.validation.summary || ''}`;
  }
  if (node.type === 'artifact') {
    const wc = (node.latestOutput || '').length;
    return `汇总完成，共 ${wc.toLocaleString()} 字。`;
  }
  return '步骤完成。';
}

/* ====================  Raw log tab  ==================== */

function RawLogTab({ node }: { node: RunNode }) {
  const log = node.streamLog || [];
  return (
    <div className="space-y-1">
      <div className="desk-label mb-2">streamLog</div>
      {log.length === 0 ? (
        <div className="text-[12px] text-desk-faint">空</div>
      ) : (
        <ul className="space-y-1">
          {log.map((e, i) => (
            <li key={i} className="text-[11px] font-mono text-desk-dim flex gap-2 leading-relaxed">
              <span className="text-desk-faint shrink-0 w-16">{fmtTime(e.ts)}</span>
              <span>
                {e.title && <span className="text-desk-text">{e.title}</span>}
                {e.title && e.summary && <span> · </span>}
                {e.summary || (e.status ?? '')}
              </span>
            </li>
          ))}
        </ul>
      )}
      {node.errorMessage && (
        <div className="mt-3 text-[12px] text-desk-danger bg-desk-danger/10 border border-desk-danger/30 rounded p-2 whitespace-pre-wrap">
          {node.errorMessage}
        </div>
      )}
    </div>
  );
}
