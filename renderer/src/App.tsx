import { useEffect, useState } from 'react';
import { DesktopShell } from '@/shell/DesktopShell';
import { useSessionStore } from '@/store/sessionStore';

export default function App() {
  const bootstrap = useSessionStore((s) => s.bootstrap);
  const [ready, setReady] = useState(false);
  const [bootError, setBootError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        await bootstrap();
        if (!cancelled) setReady(true);
      } catch (err: any) {
        if (!cancelled) setBootError(err?.message || String(err));
      }
    })();
    return () => { cancelled = true; };
  }, [bootstrap]);

  if (bootError) {
    return (
      <div className="h-screen flex items-center justify-center text-desk-danger text-sm px-6 text-center">
        启动失败：{bootError}
      </div>
    );
  }

  if (!ready) {
    return (
      <div className="h-screen flex items-center justify-center text-desk-dim text-sm">
        正在加载工作桌面…
      </div>
    );
  }

  return <DesktopShell />;
}
