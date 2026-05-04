import { BaseEdge, EdgeLabelRenderer, getSmoothStepPath, type EdgeProps } from '@xyflow/react';

const COLOR_BY_STATUS: Record<string, string> = {
  pending: '#3a4250',
  active: '#7c9cff',
  done: '#4f5566',
  failed: '#ef6b6b',
};

export default function FlowEdge(props: EdgeProps & { data?: any }) {
  const { sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, data, label } = props;
  const status = data?.status || 'pending';
  const stroke = COLOR_BY_STATUS[status];
  const isActive = status === 'active';
  const isFailed = status === 'failed';

  const [path, labelX, labelY] = getSmoothStepPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
    borderRadius: 12,
  });

  return (
    <>
      <BaseEdge
        id={props.id}
        path={path}
        style={{
          stroke,
          strokeWidth: isActive ? 1.8 : 1.4,
          strokeDasharray: isFailed ? '4 3' : undefined,
        }}
        className={isActive ? 'flow-active' : ''}
      />
      {label && (
        <EdgeLabelRenderer>
          <div
            style={{
              position: 'absolute',
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
              pointerEvents: 'none',
            }}
            className="text-[10px] text-desk-dim bg-desk-panel border border-desk-border px-1.5 py-0.5 rounded"
          >
            {label as React.ReactNode}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}
