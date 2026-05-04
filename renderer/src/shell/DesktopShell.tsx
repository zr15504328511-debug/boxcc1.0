import { useSessionStore } from '@/store/sessionStore';
import { TopBar } from './TopBar';
import { SessionDock } from './SessionDock';
import { SettingsDrawer } from './SettingsDrawer';
import { AgentsDrawer } from './AgentsDrawer';
import { TaskInputBar } from './TaskInputBar';
import { RunGraphCanvas } from '@/graph/RunGraphCanvas';
import { NodeInspector } from '@/inspector/NodeInspector';

export function DesktopShell() {
  const drawer = useSessionStore((s) => s.drawer);
  const inspectorOpen = useSessionStore((s) => !!s.inspectorNodeId);

  return (
    <div className="h-screen w-screen flex flex-col">
      <TopBar />
      <div className="flex-1 flex min-h-0">
        <SessionDock />
        <main className="flex-1 flex flex-col min-w-0">
          <div className="flex-1 flex min-h-0">
            <div className="flex-1 min-w-0 relative">
              <RunGraphCanvas />
            </div>
            {inspectorOpen && (
              <aside className="w-[380px] shrink-0 border-l border-desk-border bg-desk-panel/40 backdrop-blur">
                <NodeInspector />
              </aside>
            )}
          </div>
          <TaskInputBar />
        </main>
        {drawer && (
          <aside className="w-[360px] shrink-0 border-l border-desk-border bg-desk-panel/60 backdrop-blur">
            {drawer === 'settings' && <SettingsDrawer />}
            {drawer === 'agents' && <AgentsDrawer />}
          </aside>
        )}
      </div>
    </div>
  );
}
