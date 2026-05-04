import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));

/** @type {import('tailwindcss').Config} */
export default {
  content: [
    path.join(here, 'index.html'),
    path.join(here, 'src/**/*.{ts,tsx}'),
  ],
  theme: {
    extend: {
      colors: {
        desk: {
          bg: '#0e1116',
          panel: '#161b22',
          panel2: '#1c222b',
          border: '#2a313c',
          accent: '#7c9cff',
          accent2: '#5ad1c4',
          warn: '#f0b341',
          danger: '#ef6b6b',
          ok: '#6cd17a',
          text: '#e6edf3',
          dim: '#9aa6b2',
        },
      },
      fontFamily: {
        sans: ['"SF Pro Text"', '"PingFang SC"', '"HarmonyOS Sans"', 'system-ui', 'sans-serif'],
        mono: ['"SF Mono"', 'Menlo', 'monospace'],
      },
      boxShadow: {
        card: '0 1px 0 rgba(255,255,255,0.04) inset, 0 6px 24px rgba(0,0,0,0.35)',
      },
    },
  },
  plugins: [],
};
