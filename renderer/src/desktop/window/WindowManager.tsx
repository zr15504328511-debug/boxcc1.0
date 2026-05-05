import { useWindowStore } from './windowStore';
import { FloatingWindow } from './FloatingWindow';
import { ModelsFolder } from '../folders/ModelsFolder';
import { AgentsFolder } from '../folders/AgentsFolder';
import { SessionsFolder } from '../folders/SessionsFolder';
import { NodeDetailFolder } from '../folders/NodeDetailFolder';
import { OutputsFolder } from '../folders/OutputsFolder';

export function WindowManager() {
  const windows = useWindowStore((s) => s.windows);
  const list = Object.values(windows);

  return (
    <>
      {list.map((w) => (
        <FloatingWindow key={w.id} id={w.id}>
          {w.kind === 'models' && <ModelsFolder />}
          {w.kind === 'agents' && <AgentsFolder />}
          {w.kind === 'sessions' && <SessionsFolder />}
          {w.kind === 'node-detail' && <NodeDetailFolder nodeId={w.payload?.nodeId} />}
          {w.kind === 'outputs' && <OutputsFolder />}
        </FloatingWindow>
      ))}
    </>
  );
}
