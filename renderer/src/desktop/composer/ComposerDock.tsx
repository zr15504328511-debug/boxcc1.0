import { useState, useRef, useEffect } from 'react';
import { useSessionStore } from '@/store/sessionStore';
import { useWindowStore } from '../window/windowStore';
import { usePanelDrag, useButtonDrag } from '../useDraggable';
import { AttachmentSlot } from './AttachmentSlot';

const COMPOSER_W = 480;
const COMPOSER_BTN = 48;

function defaultPanelPos() {
  return { x: 24, y: window.innerHeight - 200 };
}
function defaultBtnPos() {
  return { x: 24, y: window.innerHeight - COMPOSER_BTN - 24 };
}

export function ComposerDock() {
  const [collapsed, setCollapsed] = useState(false);
  const [text, setText] = useState('');

  const status = useSessionStore((s) => s.status);
  const sendTask = useSessionStore((s) => s.sendTask);
  const activeProfileId = useSessionStore((s) => s.activeProfileId);
  const profiles = useSessionStore((s) => s.profiles);
  const profile = profiles.find((p) => p.id === activeProfileId);
  const toggleWindow = useWindowStore((s) => s.toggle);
  const modelsOpen = useWindowStore((s) => !!s.windows['models']);
  const agentsOpen = useWindowStore((s) => !!s.windows['agents']);

  const taRef = useRef<HTMLTextAreaElement>(null);

  // 面板态拖动（拖动 header 把手）
  const { pos: panelPos, startDrag: startPanelDrag } = usePanelDrag(defaultPanelPos());
  // 折叠按钮态拖动（点击 vs 拖动靠阈值区分）
  const { pos: btnPos, onMouseDown: btnMouseDown } = useButtonDrag(
    defaultBtnPos(),
    () => setCollapsed(false),
  );

  useEffect(() => {
    if (!collapsed) taRef.current?.focus();
  }, [collapsed]);

  useEffect(() => {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = Math.min(140, ta.scrollHeight) + 'px';
  }, [text]);

  const disabled = status === 'running' || !text.trim();

  const submit = async () => {
    if (disabled) return;
    const t = text;
    setText('');
    await sendTask(t);
  };

  if (collapsed) {
    return (
      <button
        style={{ left: btnPos.x, top: btnPos.y }}
        className="absolute z-[200] glass-composer w-12 h-12 rounded-full flex items-center justify-center text-desk-text hover:text-white cursor-grab active:cursor-grabbing"
        onMouseDown={btnMouseDown}
        title="打开任务输入 — 可拖动"
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
        </svg>
      </button>
    );
  }

  return (
    <div
      style={{ left: panelPos.x, top: panelPos.y, width: COMPOSER_W }}
      className="absolute z-[200] glass-composer no-select"
      onMouseDown={(e) => e.stopPropagation()}
      onClick={(e) => e.stopPropagation()}
    >
      {/* drag handle / header */}
      <div
        onMouseDown={startPanelDrag}
        className="flex items-center justify-between px-3 pt-2.5 pb-1.5 cursor-grab active:cursor-grabbing"
      >
        <div className="flex items-center gap-2 text-[11px] text-desk-dim">
          <span className="node-dot node-dot--running" />
          <span>给 orc 发任务</span>
          <span className="text-desk-faint text-[10px] ml-1">⋮⋮ 拖动</span>
        </div>
        <button
          className="text-desk-faint hover:text-desk-dim p-1 rounded"
          onClick={(e) => { e.stopPropagation(); setCollapsed(true); }}
          onMouseDown={(e) => e.stopPropagation()}
          title="折叠"
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <path d="M5 12h14" />
          </svg>
        </button>
      </div>

      {/* textarea */}
      <div className="px-3">
        <textarea
          ref={taRef}
          rows={1}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
              e.preventDefault();
              submit();
            }
          }}
          placeholder={profile ? '描述你的任务，让 orc 编排...' : '请先在桌面右侧"模型"图标里配置一个模型 profile'}
          className="w-full bg-transparent border-0 outline-none resize-none text-[13.5px] leading-relaxed text-desk-text placeholder:text-desk-faint px-0 py-1"
          style={{ minHeight: 28, maxHeight: 140 }}
          disabled={!profile}
        />
      </div>

      {/* tools row */}
      <div className="flex items-center justify-between px-3 pb-2.5 pt-1.5 border-t border-white/5">
        <div className="flex items-center gap-1.5">
          <AttachmentSlot kind="file" title="附件" />
          <AttachmentSlot kind="image" title="图片" />
          <button
            className={`flex items-center gap-1 text-[10.5px] px-2 py-1 rounded transition ${
              modelsOpen
                ? 'bg-white/10 text-desk-text'
                : 'text-desk-faint hover:text-desk-dim hover:bg-white/5'
            }`}
            onClick={() => toggleWindow('models')}
            title="模型配置 — 再次点击关闭"
          >
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 2 9.5 8.5 3 11l6.5 2.5L12 20l2.5-6.5L21 11l-6.5-2.5z" />
            </svg>
            <span>{profile
              ? `${profile.label || profile.provider} · ${profile.model || '未选模型'}`
              : '配置模型 →'}</span>
          </button>
          <button
            className={`flex items-center gap-1 text-[10.5px] px-2 py-1 rounded transition ${
              agentsOpen
                ? 'bg-white/10 text-desk-text'
                : 'text-desk-faint hover:text-desk-dim hover:bg-white/5'
            }`}
            onClick={() => toggleWindow('agents')}
            title="部门 / agents — 再次点击关闭"
          >
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="9" cy="8" r="3" />
              <circle cx="17" cy="9" r="2.5" />
              <path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6" />
            </svg>
            <span>部门</span>
          </button>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-desk-faint">
            {(navigator.platform || '').toLowerCase().includes('mac') ? '⌘' : 'Ctrl'} + ↵
          </span>
          <button
            className="desk-btn-primary px-3 py-1.5 text-[12px]"
            disabled={disabled}
            onClick={submit}
          >
            {status === 'running' ? (
              <span className="inline-flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-current animate-pulse" />
                运行中
              </span>
            ) : '发送'}
          </button>
        </div>
      </div>
    </div>
  );
}
