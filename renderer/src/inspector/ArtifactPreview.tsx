import ReactMarkdown from 'react-markdown';
import { api } from '@/store/ipcBridge';

export function ArtifactPreview({ content }: { content: string }) {
  if (!content) {
    return <div className="text-[12px] text-desk-dim">最终方案尚未生成。</div>;
  }
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="desk-label">artifact</span>
        <button className="desk-btn text-[11px] py-1" onClick={() => api().copyText(content)}>
          复制全文
        </button>
      </div>
      <div className="prose prose-invert prose-sm max-w-none text-[13px] leading-relaxed">
        <ReactMarkdown>{content}</ReactMarkdown>
      </div>
    </div>
  );
}
