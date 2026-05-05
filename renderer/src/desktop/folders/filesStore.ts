import { create } from 'zustand';

export type FileKind = 'doc' | 'image' | 'sheet' | 'note';

export interface FileItem {
  id: string;
  kind: FileKind;
  name: string;
  size?: number;        // bytes (optional, MVP placeholders may omit)
  position: { x: number; y: number };  // 在 OutputsFolder 画布内的位置
  thumb?: string;        // base64 / blob url, 可选
  createdAt: number;
}

interface FilesStore {
  files: Record<string, FileItem>;
  add: (file: Omit<FileItem, 'createdAt'>) => void;
  setPosition: (id: string, pos: { x: number; y: number }) => void;
  remove: (id: string) => void;
  clear: () => void;
}

export const useFilesStore = create<FilesStore>((set) => ({
  files: {},
  add: (file) => set((s) => ({ files: { ...s.files, [file.id]: { ...file, createdAt: Date.now() } } })),
  setPosition: (id, position) => set((s) => {
    const f = s.files[id];
    if (!f) return s;
    return { files: { ...s.files, [id]: { ...f, position } } };
  }),
  remove: (id) => set((s) => {
    const { [id]: _, ...rest } = s.files;
    return { files: rest };
  }),
  clear: () => set({ files: {} }),
}));
