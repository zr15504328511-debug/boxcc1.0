import { create } from 'zustand';
import type {
  AgentSpec,
  ProfileSpec,
  ProviderSpec,
  RuntimeModel,
  SessionRecord,
  StreamEvent,
} from '@/types/boxccApi';
import {
  applyEvent,
  ensureDirectAnswerFallback,
  startRun,
} from '@/adapter/graphAdapter';
import { emptyRunGraph, nodeIdFor, type RunGraph } from '@/adapter/runGraph';
import { DEFAULT_BOOKMARK_COLORS } from '@/theme/tokens';
import { api } from './ipcBridge';

interface SessionGraphState {
  graph: RunGraph;
  positions: Record<string, { x: number; y: number }>;
}

interface State {
  // backend-facing
  sessions: SessionRecord[];
  activeSessionId: string | null;
  agents: AgentSpec[];
  profiles: ProfileSpec[];
  activeProfileId: string | null;
  providers: ProviderSpec[];

  // graph state, keyed by session id
  graphsBySession: Record<string, SessionGraphState>;

  // bookmark color customization (per agent id, persisted to local state)
  bookmarkColors: Record<string, string>;

  // ui
  inspectorNodeId: string | null;
  drawer: 'settings' | 'agents' | null;
  status: 'idle' | 'running' | 'error';
  errorMessage: string | null;

  // actions
  bootstrap: () => Promise<void>;
  selectSession: (id: string) => void;
  newSession: () => Promise<void>;
  renameSession: (id: string, title: string) => void;
  deleteSession: (id: string) => void;
  sendTask: (text: string) => Promise<void>;
  setInspectorNode: (id: string | null) => void;
  setDrawer: (d: State['drawer']) => void;
  saveProfiles: (next: ProfileSpec[]) => Promise<void>;
  setActiveProfile: (id: string | null) => void;
  saveAgents: (next: AgentSpec[]) => Promise<void>;
  setNodePosition: (nodeId: string, pos: { x: number; y: number }) => void;
  refreshModelsFor: (profileId: string) => Promise<void>;
  setBookmarkColor: (agentId: string, hex: string) => void;
}

const defaultGraphState: SessionGraphState = { graph: emptyRunGraph(), positions: {} };

function activeRuntimeModelFromProfile(profile: ProfileSpec | undefined): RuntimeModel | null {
  if (!profile) return null;
  return {
    provider: profile.provider,
    model_name: profile.model || undefined,
    api_key: profile.apiKey || undefined,
    base_url: profile.baseUrl || undefined,
    temperature: profile.temperature,
    max_tokens: profile.maxTokens,
  };
}

export const useSessionStore = create<State>((set, get) => ({
  sessions: [],
  activeSessionId: null,
  agents: [],
  profiles: [],
  activeProfileId: null,
  providers: [],
  graphsBySession: {},
  bookmarkColors: { ...DEFAULT_BOOKMARK_COLORS },
  inspectorNodeId: null,
  drawer: null,
  status: 'idle',
  errorMessage: null,

  bootstrap: async () => {
    const [state, providers, agents, profiles] = await Promise.all([
      api().loadState(),
      api().listProviders(),
      api().loadAgents(),
      api().loadProfiles(),
    ]);

    let sessions: SessionRecord[] = state.sessions || [];
    if (sessions.length === 0) {
      const created = await api().createSession({});
      sessions = [created];
    }

    const activeId = state.activeSessionId || sessions[0]?.id || null;

    // restore graph snapshots
    const graphsBySession: Record<string, SessionGraphState> = {};
    for (const s of sessions) {
      const snap = (s as any).graphSnapshot as SessionGraphState | undefined;
      graphsBySession[s.id] = snap?.graph
        ? { graph: snap.graph, positions: snap.positions || {} }
        : { ...defaultGraphState };
    }

    const persistedColors = (state as any).bookmarkColors as Record<string, string> | undefined;

    set({
      sessions,
      activeSessionId: activeId,
      providers,
      agents: agents || state.agents || [],
      profiles: profiles || state.profiles || [],
      activeProfileId: state.activeProfileId || profiles?.[0]?.id || null,
      graphsBySession,
      bookmarkColors: { ...DEFAULT_BOOKMARK_COLORS, ...(persistedColors || {}) },
    });
  },

  selectSession: (id) => {
    set({ activeSessionId: id, inspectorNodeId: null });
    void persistState(get);
  },

  newSession: async () => {
    const created = await api().createSession({});
    set((s) => ({
      sessions: [...s.sessions, created],
      activeSessionId: created.id,
      graphsBySession: { ...s.graphsBySession, [created.id]: { ...defaultGraphState } },
      inspectorNodeId: null,
    }));
    void persistState(get);
  },

  renameSession: (id, title) => {
    set((s) => ({
      sessions: s.sessions.map((x) => (x.id === id ? { ...x, title } : x)),
    }));
    void persistSessions(get);
  },

  deleteSession: (id) => {
    set((s) => {
      const remaining = s.sessions.filter((x) => x.id !== id);
      const nextActive = s.activeSessionId === id ? remaining[0]?.id || null : s.activeSessionId;
      const { [id]: _, ...restGraphs } = s.graphsBySession;
      return {
        sessions: remaining,
        activeSessionId: nextActive,
        graphsBySession: restGraphs,
      };
    });
    void persistState(get);
  },

  sendTask: async (text: string) => {
    const { activeSessionId, profiles, activeProfileId } = get();
    if (!activeSessionId || !text.trim()) return;

    const runSessionId = activeSessionId;
    const profile = profiles.find((p) => p.id === activeProfileId);
    const runtimeModel = activeRuntimeModelFromProfile(profile);

    const runId = `run-${Date.now()}`;
    set((s) => ({
      status: 'running',
      errorMessage: null,
      graphsBySession: {
        ...s.graphsBySession,
        [runSessionId]: {
          ...(s.graphsBySession[runSessionId] || defaultGraphState),
          graph: startRun(emptyRunGraph(), { runId, userText: text }),
        },
      },
    }));

    let streamRequestId: string | null = null;
    const dispose = api().onChatStreamEvent((ev: StreamEvent) => {
      if (!streamRequestId || ev.requestId !== streamRequestId) return;
      const cur = get().graphsBySession[runSessionId] || defaultGraphState;
      const nextGraph = applyEvent(cur.graph, ev);
      set((s) => ({
        graphsBySession: {
          ...s.graphsBySession,
          [runSessionId]: { ...cur, graph: nextGraph },
        },
      }));

      if (ev.type === 'done') {
        const latest = get().graphsBySession[runSessionId] || defaultGraphState;
        const finalized = ensureDirectAnswerFallback(latest.graph);
        set((s) => ({
          status: 'idle',
          graphsBySession: {
            ...s.graphsBySession,
            [runSessionId]: { ...latest, graph: finalized },
          },
        }));
        // append a synthetic message so the session list shows recent activity
        appendSessionMessages(get, runSessionId, text, finalized.finalAnswer || '');
        void persistState(get);
        dispose();
      }
      if (ev.type === 'error') {
        set({ status: 'error', errorMessage: ev.error || 'Unknown error' });
        void persistState(get);
        dispose();
      }
    });

    const result = await api().startChatStream({
      sessionId: activeSessionId,
      message: text,
      runtimeModel,
    });
    streamRequestId = result.requestId || null;
    if (!result.ok) {
      set({ status: 'error', errorMessage: result.error || '后端启动失败' });
      dispose();
    }
  },

  setInspectorNode: (id) => set({ inspectorNodeId: id }),
  setDrawer: (d) => set({ drawer: d }),

  saveProfiles: async (next) => {
    set({ profiles: next });
    await api().saveProfiles(next);
  },
  setActiveProfile: (id) => {
    set({ activeProfileId: id });
    void persistState(get);
  },
  saveAgents: async (next) => {
    set({ agents: next });
    await api().saveAgents(next);
  },

  setNodePosition: (nodeId, pos) => {
    const { activeSessionId } = get();
    if (!activeSessionId) return;
    set((s) => {
      const cur = s.graphsBySession[activeSessionId] || defaultGraphState;
      return {
        graphsBySession: {
          ...s.graphsBySession,
          [activeSessionId]: {
            ...cur,
            positions: { ...cur.positions, [nodeId]: pos },
          },
        },
      };
    });
    void persistState(get);
  },

  setBookmarkColor: (agentId, hex) => {
    set((s) => ({ bookmarkColors: { ...s.bookmarkColors, [agentId]: hex } }));
    void persistState(get);
  },

  refreshModelsFor: async (profileId: string) => {
    const profile = get().profiles.find((p) => p.id === profileId);
    if (!profile) return;
    const result = await api().listModelsForProfile(profile);
    if (result.ok && Array.isArray(result.models)) {
      const next = get().profiles.map((p) =>
        p.id === profileId ? { ...p, models: result.models } : p,
      );
      set({ profiles: next });
      await api().saveProfiles(next);
    }
  },
}));

function appendSessionMessages(
  get: () => State,
  sessionId: string,
  userText: string,
  assistantText: string,
) {
  const sessions = get().sessions.map((s) =>
    s.id === sessionId
      ? {
          ...s,
          title: s.title === '新会话' || !s.title ? userText.slice(0, 24) : s.title,
          messages: [
            ...(s.messages || []),
            {
              id: `u-${Date.now()}`,
              role: 'user' as const,
              content: userText,
              createdAt: new Date().toISOString(),
            },
            {
              id: `a-${Date.now()}`,
              role: 'assistant' as const,
              content: assistantText,
              createdAt: new Date().toISOString(),
            },
          ],
          updatedAt: new Date().toISOString(),
        }
      : s,
  );
  useSessionStore.setState({ sessions });
  void api().saveSessions(sessions);
}

async function persistSessions(get: () => State) {
  const { sessions, graphsBySession } = get();
  const enriched = sessions.map((s) => ({
    ...s,
    graphSnapshot: graphsBySession[s.id] || null,
  }));
  await api().saveSessions(enriched);
}

async function persistState(get: () => State) {
  const { sessions, activeSessionId, profiles, activeProfileId, agents, graphsBySession, bookmarkColors } = get();
  const enriched = sessions.map((s) => ({
    ...s,
    graphSnapshot: graphsBySession[s.id] || null,
  }));
  await api().saveSessions(enriched);
  await api().saveState({
    sessions: enriched,
    activeSessionId,
    profiles,
    activeProfileId,
    agents,
    bookmarkColors,
  } as any);
}

const FALLBACK_GRAPH = emptyRunGraph();
const FALLBACK_POSITIONS: Record<string, { x: number; y: number }> = {};

export const selectActiveGraph = (s: State): RunGraph =>
  (s.activeSessionId && s.graphsBySession[s.activeSessionId]?.graph) || FALLBACK_GRAPH;

export const selectActivePositions = (s: State): Record<string, { x: number; y: number }> =>
  (s.activeSessionId && s.graphsBySession[s.activeSessionId]?.positions) || FALLBACK_POSITIONS;

export { nodeIdFor };
