// Mirror of preload.js — keep field names in sync with main process IPC contract.

export type AgentPhase = 'lead' | 'worker' | 'critic';

export interface AgentSpec {
  id: string;
  name: string;
  display_name?: string;
  description?: string;
  desc?: string;
  enabled: boolean;
  instructions?: string;
  isDefault?: boolean;
  binding?: string;
  phase?: AgentPhase;
  nativeName?: string;
  skill_packs?: string[];
}

export interface ProviderSpec {
  id: string;
  label: string;
  default_base_url?: string;
}

export interface ProfileSpec {
  id: string;
  provider: string;
  baseUrl?: string;
  apiKey?: string;
  model?: string;
  models?: string[];
  label?: string;
  temperature?: number;
  maxTokens?: number;
}

export interface RuntimeModel {
  provider?: string;
  model_name?: string;
  api_key?: string;
  base_url?: string;
  temperature?: number;
  max_tokens?: number;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  createdAt: string;
}

export interface SessionRecord {
  id: string;
  title: string;
  messages: ChatMessage[];
  graphSnapshot?: unknown;
  createdAt?: string;
  updatedAt?: string;
}

export interface AppState {
  sessions: SessionRecord[];
  activeSessionId?: string | null;
  agents?: AgentSpec[];
  profiles?: ProfileSpec[];
  activeProfileId?: string | null;
  uiTheme?: string;
}

export interface StreamEvent {
  requestId?: string;
  type: string;
  message_id?: string;
  delta?: string;
  step_id?: string;
  phase?: 'orc' | 'worker' | 'critic' | 'final';
  agent_id?: string;
  node_id?: string;
  status?: 'running' | 'completed' | 'failed' | 'pending' | 'timed_out' | 'reworking' | 'needs_rework' | 'validated';
  title?: string;
  summary?: string;
  meta?: Record<string, unknown>;
  content?: string;
  task_packet?: any;
  available_skill_packs?: string[];
  is_rework?: boolean;
  elapsed_ms?: number;
  task_type?: string;
  last_run_status?: string;
  selected_workers?: string[];
  checklist?: any[];
  error?: string;
  message?: any;
  department_results?: Array<{
    agent_id?: string;
    name?: string;
    content?: string;
    error?: string;
    task_packet?: any;
  }>;
  workflow_artifact?: any;
}

export interface BoxccApi {
  loadState: () => Promise<AppState>;
  saveState: (payload: Partial<AppState>) => Promise<void>;
  loadSessions: () => Promise<SessionRecord[]>;
  saveSessions: (payload: SessionRecord[]) => Promise<void>;
  createSession: (payload?: { title?: string }) => Promise<SessionRecord>;
  loadProfiles: () => Promise<ProfileSpec[]>;
  saveProfiles: (payload: ProfileSpec[]) => Promise<void>;
  loadAgents: () => Promise<AgentSpec[]>;
  saveAgents: (payload: AgentSpec[]) => Promise<void>;
  listProviders: () => Promise<ProviderSpec[]>;
  validateProfile: (payload: ProfileSpec) => Promise<{ ok: boolean; error?: string }>;
  listModelsForProfile: (payload: ProfileSpec) => Promise<{ ok: boolean; models?: string[]; error?: string }>;
  sendChat: (payload: any) => Promise<any>;
  startChatStream: (payload: any) => Promise<{ ok: boolean; requestId?: string; error?: string }>;
  onChatStreamEvent: (handler: (payload: StreamEvent) => void) => () => void;
  copyText: (payload: string) => Promise<boolean>;
}

declare global {
  interface Window {
    boxccAPI: BoxccApi;
  }
}

export {};
