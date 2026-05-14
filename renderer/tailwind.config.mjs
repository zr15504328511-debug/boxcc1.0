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
          bg: '#0a0d12',
          surface: '#11172a',
          panel: 'rgba(20,24,36,0.62)',
          border: 'rgba(255,255,255,0.10)',
          accent: '#7c9cff',
          accent2: '#5ad1c4',
          warn: '#f0b341',
          danger: '#ef6b6b',
          ok: '#5dd29b',
          text: '#e6edf3',
          dim: '#9aa6b6',
          faint: '#5d6678',
        },
        agent: {
          orc: '#7c9cff',
          dom: '#5ad1c4',
          pln: '#f0b341',
          ana: '#c39bff',
          cpy: '#ff8aae',
          crt: '#f0b341',
          user: '#9aa6b6',
          artifact: '#5dd29b',
        },
      },
      fontFamily: {
        sans: ['"SF Pro Text"', '"PingFang SC"', '"HarmonyOS Sans"', 'system-ui', 'sans-serif'],
        mono: ['"SF Mono"', 'Menlo', 'monospace'],
      },
      boxShadow: {
        glass: '0 4px 14px rgba(0,0,0,0.30), 0 0 0 1px rgba(255,255,255,0.04) inset',
        glow: '0 0 0 1px rgba(124,156,255,0.32)',
      },
    },
  },
  plugins: [],
};
