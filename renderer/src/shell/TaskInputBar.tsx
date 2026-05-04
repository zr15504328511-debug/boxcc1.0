import { useState } from 'react';
import { useSessionStore } from '@/store/sessionStore';

export function TaskInputBar() {
  const [text, setText] = useState('');
  const status = useSessionStore((s) => s.status);
  const sendTask = useSessionStore((s) => s.sendTask);
  const activeProfileId = useSessionStore((s) => s.activeProfileId);
  const profiles = useSessionStore((s) => s.profiles);
  const profile = profiles.find((p) => p.id === activeProfileId);

  const disabled = status === 'running' || !text.trim();

  const submit = async () => {
    if (disabled) return;
    const t = text;
    setText('');
    await sendTask(t);
  };

  return (
    <div className="border-t border-desk-border bg-desk-panel/60 backdrop-blur px-4 py-3">
      <div className="flex items-end gap-2">
        <textarea
          className="desk-input min-h-[44px] max-h-32 resize-none"
          rows={1}
          placeholder={profile ? `给 orc 发任务（${profile.label || profile.provider}/${profile.model || '未选模型'}）— Ctrl+Enter 发送` : '请先在右上「模型」配置一个模型 profile'}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
              e.preventDefault();
              submit();
            }
          }}
        />
        <button className="desk-btn-primary" disabled={disabled} onClick={submit}>
          {status === 'running' ? '运行中...' : '发送'}
        </button>
      </div>
    </div>
  );
}
