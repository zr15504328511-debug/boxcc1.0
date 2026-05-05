import { useEffect } from 'react';
import { useSessionStore, selectActiveGraph } from '@/store/sessionStore';
import { useWindowStore } from './window/windowStore';
import { usePacketStore } from './packets/usePacketStore';
import { DesktopBackground } from './DesktopBackground';
import { MenuBar } from './MenuBar';
import { ComposerDock } from './composer/ComposerDock';
import { WindowManager } from './window/WindowManager';
import { BookmarkStrip } from './bookmarks/BookmarkStrip';
import { PacketLayer } from './packets/PacketLayer';
import { OutputsFolderButton } from './OutputsFolderButton';

export function Desktop() {
  const profiles = useSessionStore((s) => s.profiles);
  const openWindow = useWindowStore((s) => s.open);
  const closeAll = useWindowStore((s) => s.closeAll);
  const hidePackets = usePacketStore((s) => s.hide);
  const graph = useSessionStore(selectActiveGraph);
  const isEmpty = Object.keys(graph.nodes).length === 0;

  // 第一次启动如果没有 profile，自动弹出模型浮窗
  useEffect(() => {
    if (profiles.length === 0) {
      openWindow('models');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div
      className="absolute inset-0 overflow-hidden"
      onMouseDown={(e) => {
        const target = e.target as HTMLElement;
        if (target.closest('[data-floating-window]')) return;
        if (target.closest('[data-bookmark-strip]')) return;
        // 点击桌面空白处 → 关闭所有浮窗 + 隐藏（不删除）通信卡片
        closeAll();
        hidePackets();
      }}
    >
      <DesktopBackground />
      <MenuBar />

      <div className="absolute inset-0 pt-7">
        <PacketLayer />
        {isEmpty && (
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
            <div className="text-center max-w-[420px] px-6">
              <div className="text-[15px] font-medium text-desk-dim">桌面空着</div>
              <div className="text-[13px] mt-2 leading-relaxed text-desk-faint">
                在左下角对话框给 orc 发一个任务，<br/>
                右侧书签会随 agent 激活点亮，<br/>
                通信卡片会从书签飞向桌面中央。
              </div>
            </div>
          </div>
        )}
      </div>

      <BookmarkStrip />
      <OutputsFolderButton />
      <ComposerDock />
      <WindowManager />
    </div>
  );
}
