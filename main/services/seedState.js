// Agents are now sourced from the backend via GET /api/agents.
// This seed only contains the orc shell so the UI has something to render
// before the first fetch resolves. Real agent metadata (id, name, one_liner,
// tags, kb_refs) lives in backend/config.yaml `agents.registry` and is
// editable via the future Agent Creator UI.
const defaultAgents = [
  {
    id: 'orc',
    name: '主席团',
    desc: '负责任务分发、结果汇总与最终输出',
    enabled: true,
    instructions: '负责理解用户问题，决定启用哪些 agent，并整合最终结果。',
    isDefault: true,
    binding: 'auto',
  },
];

const defaultProfiles = [
  {
    id: 'p1',
    name: '个人配置1',
    provider: 'OpenAI',
    baseUrl: '',
    apiKey: '',
    model: 'gpt-4o',
  },
];

const defaultSessions = [
  {
    id: '1',
    title: '2024夏季面料企划',
    updatedAt: '14:20',
    summary: '亚麻混纺评估',
    memorySummary: '当前重点：面料耐磨性与色牢度。',
    uploads: [{ id: 'f1', name: '夏装报价表.xlsx', size: '24KB' }],
    messages: [],
    agentContexts: {},
  },
];

module.exports = {
  defaultAgents,
  defaultProfiles,
  defaultSessions,
};
