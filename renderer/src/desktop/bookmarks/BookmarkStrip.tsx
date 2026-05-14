import { useEffect, useMemo, useRef, useState } from 'react';
import { useSessionStore } from '@/store/sessionStore';
import { AgentBookmark } from './AgentBookmark';
import { AddBookmarkSlot } from './AddBookmarkSlot';
import { SweepEffectLayer } from './SweepEffectLayer';
import { deriveRoster } from './agentRoster';

const BOOKMARK_W = 58;
const PEEK_VISIBLE = 8;
const PEEK = BOOKMARK_W - PEEK_VISIBLE;
const SLIDE_OUT_MS = 220;
const SENSOR_W = 14;

export function BookmarkStrip() {
  const agents = useSessionStore((s) => s.agents);
  const roster = useMemo(() => deriveRoster(agents), [agents]);
  const rosterAgentIds = useMemo(
    () => roster.map((e) => (e.kind === 'agent' ? e.spec.agentId : '__add__')),
    [roster],
  );

  const [hovered, setHovered] = useState(false);
  const [forceShow, setForceShow] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (hovered) return;
    const t = setTimeout(() => setForceShow(false), SLIDE_OUT_MS + 50);
    return () => clearTimeout(t);
  }, [hovered]);

  const expanded = hovered || forceShow;

  return (
    <>
      {/* 屏幕右边缘 hover 触发区 */}
      {!expanded && (
        <div
          className="absolute top-0 right-0 bottom-0 z-[148]"
          style={{ width: SENSOR_W }}
          onMouseEnter={() => { setHovered(true); setForceShow(true); }}
        />
      )}

      <div
        ref={ref}
        data-bookmark-strip
        className={`absolute right-0 top-1/2 -translate-y-1/2 z-[150] flex flex-col gap-2 no-select ${
          expanded ? 'bookmark-strip-expanded' : 'bookmark-strip-collapsed'
        }`}
        style={{
          transform: expanded ? 'translate(0, -50%)' : `translate(${PEEK}px, -50%)`,
          transition: `transform ${SLIDE_OUT_MS}ms cubic-bezier(0.22, 1, 0.36, 1)`,
        }}
        onMouseEnter={() => { setHovered(true); setForceShow(true); }}
        onMouseLeave={() => setHovered(false)}
        onMouseDown={(e) => e.stopPropagation()}
      >
        {/* 扫光层 — 覆盖整个 strip，事件传递不影响 */}
        <SweepEffectLayer rosterAgentIds={rosterAgentIds} />

        {roster.map((entry, i) => {
          if (entry.kind === 'agent') {
            return <AgentBookmark key={`a-${entry.spec.agentId}`} spec={entry.spec} />;
          }
          return <AddBookmarkSlot key={`add-${i}`} />;
        })}
      </div>
    </>
  );
}
