import { useSessionStore, selectActiveGraph } from '@/store/sessionStore';
import { TaskPacketView } from './TaskPacketView';
import { StreamingOutputView } from './StreamingOutputView';
import { CritiqueView } from './CritiqueView';
import { ArtifactPreview } from './ArtifactPreview';

const TYPE_LABEL: Record<string, string> = {
  user: '用户任务',
  orc: '编排 / 主席团',
  worker: '部门 worker',
  critic: '质检 critic',
  artifact: '最终交付',
};

export function NodeInspector() {
  const graph = useSessionStore(selectActiveGraph);
  const activeId = useSessionStore((s) => s.inspectorNodeId);
  const setInspector = useSessionStore((s) => s.setInspectorNode);
  const node = activeId ? graph.nodes[activeId] : undefined;

  if (!node) {
    return (
      <div className="h-full flex items-center justify-center px-6 text-center text-desk-dim text-sm">
        点击画布中的任意节点查看详情。
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      <div className="px-4 py-3 border-b border-desk-border flex items-start justify-between gap-2">
        <div>
          <div className="text-[10px] uppercase tracking-wider text-desk-dim">{TYPE_LABEL[node.type]}</div>
          <div className="text-base font-semibold mt-0.5">{node.title}</div>
          <div className="text-[11px] text-desk-dim mt-1">id: {node.id} · status: {node.status}</div>
        </div>
        <button className="desk-btn text-[11px]" onClick={() => setInspector(null)}>
          关闭
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-6">
        {node.type === 'user' && (
          <section>
            <div className="desk-label mb-1">原始请求</div>
            <div className="text-[13px] leading-relaxed whitespace-pre-wrap">{node.latestOutput}</div>
          </section>
        )}

        {(node.type === 'worker' || node.type === 'orc') && (
          <section className="desk-card p-3">
            <div className="text-[12px] font-semibold mb-2">任务包 task_packet</div>
            <TaskPacketView packet={node.taskPacket} />
          </section>
        )}

        {node.type === 'worker' && node.latestOutput && (
          <section className="desk-card p-3">
            <div className="text-[12px] font-semibold mb-2">最新输出</div>
            <div className="text-[12px] leading-relaxed whitespace-pre-wrap">{node.latestOutput}</div>
          </section>
        )}

        {node.type === 'critic' && (
          <section className="desk-card p-3">
            <div className="text-[12px] font-semibold mb-2">质检结论 ValidationReport</div>
            <CritiqueView report={node.validation} />
          </section>
        )}

        {node.type === 'artifact' && (
          <section className="desk-card p-3">
            <div className="text-[12px] font-semibold mb-2">最终方案</div>
            <ArtifactPreview content={node.latestOutput || ''} />
          </section>
        )}

        <section className="desk-card p-3">
          <StreamingOutputView node={node} />
        </section>
      </div>
    </div>
  );
}
