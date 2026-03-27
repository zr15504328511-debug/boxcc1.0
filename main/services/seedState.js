const defaultAgents = [
  {
    id: 'orc',
    name: '主席团',
    desc: '负责任务分发、结果汇总与最终输出',
    enabled: true,
    instructions: '负责理解用户问题，决定启用哪些部门，并整合最终结果。',
    isDefault: true,
    binding: 'auto',
  },
  {
    id: 'dom',
    name: '学术部',
    desc: '负责服装专业知识与工艺判断',
    enabled: true,
    instructions: '负责面料、工艺、版型、尺码与专业可行性判断。',
    isDefault: true,
    binding: 'auto',
  },
  {
    id: 'pln',
    name: '企划部',
    desc: '负责企划结构、SKU 与波段规划',
    enabled: true,
    instructions: '负责企划结构、系列组合、SKU 矩阵与开发排期。',
    isDefault: true,
    binding: 'auto',
  },
  {
    id: 'ana',
    name: '经营部',
    desc: '负责价格、成本与经营分析',
    enabled: true,
    instructions: '负责价格带、成本、毛利、竞品与经营测算。',
    isDefault: true,
    binding: 'auto',
  },
  {
    id: 'crt',
    name: '质检部',
    desc: '负责风控、挑错与复核',
    enabled: true,
    instructions: '负责检查逻辑冲突、风险点、执行可行性并提出修正意见。',
    isDefault: true,
    binding: 'auto',
  },
  {
    id: 'cpy',
    name: '宣传部',
    desc: '负责卖点翻译与传播表达',
    enabled: true,
    instructions: '负责卖点提炼、消费者表达与传播文案输出。',
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
