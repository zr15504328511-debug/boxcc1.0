# boxcc (Workbench App) 项目说明书

> 面向 AI 阅读的技术规格文档。最后更新: 2026-03-24

---

## 1. 项目概述

**boxcc** 是一个服装企划协作桌面应用。用户输入企划需求，系统通过多 Agent 协作（主席团分发 → 部门并行分析 → 风控审查）给出专业回答。

- **定位**: 服装行业企划工作台
- **架构**: Electron 桌面壳 + Python FastAPI 后端
- **核心能力**: 多 Agent 并行分析、长期记忆、上下文压缩、自动标题

---

## 2. 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 桌面壳 | Electron | 主进程 main.js 管理窗口和 IPC |
| 前端 | React 18 + Babel (browser) | 单文件 index.html，浏览器端编译 |
| 样式 | Tailwind CSS (CDN) + CSS Variables | 双主题: win98 / mac |
| 前后桥接 | preload.js (contextBridge) | 暴露 boxccAPI 对象 |
| 后端 | Python 3.11+ / FastAPI / uvicorn | 端口 18900，由 Electron 子进程启动 |
| AI 框架 | LangChain + LangGraph | Agent 编排、中间件管道 |
| 模型 | 可配置（默认 DeepSeek V3） | 通过 config.yaml use: 字段动态加载 |
| 持久化 | JSON 文件 + SQLite | 状态/记忆=JSON，会话检查点=SQLite |

---

## 3. 目录结构

```
workbench-app/
├── main.js                          # Electron 主进程
├── preload.js                       # 上下文桥接（boxccAPI）
├── index.html                       # 前端单文件（React 18 + Babel）
├── package.json                     # Electron 依赖
│
├── main/services/                   # Node.js 本地服务（状态持久化）
│   ├── stateService.js              #   整体状态读写
│   ├── sessionService.js            #   会话 CRUD
│   ├── profileRegistryService.js    #   API 配置管理
│   ├── agentService.js              #   Agent 定义管理
│   ├── providerResolverService.js   #   供应商验证
│   ├── paths.js                     #   数据目录路径
│   ├── defaultState.js              #   默认状态
│   └── seedState.js                 #   初始种子数据
│
├── data/                            # 运行时数据（gitignored）
│   └── state.json                   #   前端状态持久化
│
└── backend/                         # Python 后端
    ├── pyproject.toml               #   Python 依赖声明
    ├── config.yaml                  #   主配置文件
    ├── .env                         #   API Keys（gitignored）
    │
    ├── data/                        #   后端运行时数据（gitignored）
    │   ├── memory.json              #     长期记忆存储
    │   └── checkpoints.db           #     LangGraph 会话检查点
    │
    ├── app/                         #   FastAPI 应用
    │   ├── main.py                  #     应用工厂 + uvicorn 入口
    │   └── routers/
    │       ├── health.py            #     GET /health
    │       ├── chat.py              #     POST /api/chat（核心）
    │       ├── models.py            #     GET /api/models
    │       ├── agents.py            #     GET /api/agents
    │       └── memory.py            #     GET/PUT /api/memory
    │
    ├── agents/                      #   Agent 系统
    │   ├── lead_agent.py            #     主 Agent 工厂（LangGraph）
    │   ├── thread_state.py          #     ThreadState 状态定义
    │   ├── prompt.py                #     系统提示词构建
    │   ├── middlewares/
    │   │   ├── tool_error_middleware.py      # 工具异常恢复
    │   │   ├── title_middleware.py           # 自动标题生成
    │   │   ├── memory_middleware.py          # 记忆注入+提取
    │   │   └── loop_detection_middleware.py  # 循环调用检测
    │   └── memory/
    │       ├── updater.py           #     LLM 记忆提取
    │       ├── queue.py             #     防抖更新队列（30s）
    │       └── prompt.py            #     记忆提取/注入模板
    │
    ├── subagents/                   #   部门子 Agent
    │   ├── config.py                #     SubagentConfig 数据类
    │   ├── registry.py              #     从 config.yaml 加载部门定义
    │   ├── executor.py              #     并行执行引擎（asyncio）
    │   └── tools.py                 #     delegate_to_departments 工具
    │
    ├── models/
    │   └── factory.py               #   create_chat_model() 多供应商工厂
    │
    └── config/
        ├── app_config.py            #   Pydantic 配置 + YAML 加载
        └── paths.py                 #   后端数据目录路径
```

---

## 4. 数据流

### 4.1 启动流程

```
用户双击应用
  → Electron main.js 启动
  → 注册 IPC handlers（本地状态服务）
  → spawn('python', ['-m', 'app.main']) 启动 Python 子进程
  → Python: FastAPI 启动，加载 config.yaml，监听 18900
  → main.js 轮询 GET /health（500ms 间隔，30s 超时）
  → 健康检查通过 → 创建 BrowserWindow → 加载 index.html
  → React 挂载 → loadState() 恢复持久化数据
```

### 4.2 消息发送流程

```
用户输入 → handleSend()
  → 立即显示用户消息气泡
  → window.boxccAPI.sendChat({ sessionId, message, modelName })
  → [preload.js] ipcRenderer.invoke('chat:send', payload)
  → [main.js] HTTP POST → Python /api/chat
  → [Python] Lead Agent (LangGraph) 处理:
      1. 中间件 before: 注入记忆
      2. LLM #1: 主席团阅读问题，生成 chairman_plan
      3. 工具调用: delegate_to_departments
         a. Phase 1: 4 个工作部门并行（Semaphore=3）
         b. Phase 2: 风控部审查所有结果
      4. LLM #2: 主席团综合结果，生成最终回答
      5. 中间件 after: 生成标题、入队记忆提取
  → 返回 { ok, message, title }
  → [main.js] 整形为 { ok, userMessage, assistantMessage, title }
  → [index.html] 追加 assistantMessage 到 session.messages
  → 更新标题，自动保存状态（120ms 防抖）
```

### 4.3 关闭流程

```
用户关闭窗口
  → will-quit 事件
  → taskkill Python 子进程
  → Python lifespan shutdown: MemoryUpdateQueue.flush()
  → Electron 退出
```

---

## 5. Agent 架构

### 5.1 六部门体系

| ID | 名称 | 角色 | 执行阶段 |
|----|------|------|---------|
| orc | 主席团 Orchestrator | 任务理解、分发、综合 | Lead Agent 自身承担，不是独立子 Agent |
| dom | 学术部 Domain Expert | 面料、工艺、版型专业知识 | Phase 1 并行 |
| pln | 企划部 Planner | SKU、波段、系列结构规划 | Phase 1 并行 |
| ana | 经营部 Analyst | 价格、成本、毛利分析 | Phase 1 并行 |
| cpy | 宣传部 Copywriter | 文案、卖点、传播表达 | Phase 1 并行 |
| crt | 风控部 Critic | 审查矛盾、风险、可行性 | Phase 2 串行（在所有工作部门完成后） |

### 5.2 执行流程

```
用户问题
  ↓
[Lead Agent = orc 主席团]
  ├─ LLM 调用: 理解问题，为每个部门分配任务
  ├─ 调用 delegate_to_departments 工具:
  │   ├─ Phase 1: dom + pln + ana + cpy 并行执行（max_concurrent=3）
  │   │   每个部门是独立的 LangGraph Agent，有自己的 system_prompt
  │   │   即使"无需行动"也必须被调用
  │   └─ Phase 2: crt 风控部审查所有 Phase 1 结果
  └─ LLM 调用: 综合所有结果 + 风控意见，生成最终回答
```

### 5.3 中间件管道（5 层）

执行顺序（before_model 阶段正序，after_agent 阶段逆序）:

| # | 中间件 | before_model | after_agent |
|---|--------|-------------|-------------|
| 1 | ToolErrorMiddleware | - | 捕获工具异常，转为错误消息 |
| 2 | SummarizationMiddleware | 检查 token 数 | 超过 12000 token 时自动压缩历史 |
| 3 | TitleMiddleware | - | 首次对话后异步生成标题 |
| 4 | MemoryMiddleware | 注入记忆到 system prompt | 将对话入队异步记忆提取 |
| 5 | LoopDetectionMiddleware | 检查重复工具调用 | 3 次警告，5 次强制停止 |

---

## 6. 配置系统

### 6.1 config.yaml 结构

```yaml
config_version: 1

models:                        # 可用 LLM 模型列表
  - name: deepseek-v3          # 唯一标识
    display_name: DeepSeek V3  # 显示名
    use: langchain_openai:ChatOpenAI  # Python 类路径（动态导入）
    model: deepseek-chat       # 传给 LLM 的 model 参数
    api_key: $DEEPSEEK_API_KEY # $开头=读环境变量
    base_url: https://...      # API 端点
    max_tokens: 8192
    temperature: 0.7

departments:
  max_concurrent: 3            # 并行上限
  timeout_seconds: 300         # 单部门超时
  agents:                      # 部门定义列表
    - id: dom
      name: 学术部
      display_name: Domain Expert
      description: ...
      enabled: true            # false = 跳过该部门
      model: inherit           # inherit = 用主 Agent 的模型
      system_prompt: |         # 部门 Agent 的系统提示词
        ...
      max_turns: 25            # LangGraph 递归限制

lead_agent:
  system_prompt: |             # 主席团提示词（含 {departments_description} 占位符）
    ...

summarization:
  enabled: true
  max_token_threshold: 12000   # 超过此值触发压缩
  keep_recent_messages: 8      # 压缩时保留最近 N 条

memory:
  enabled: true
  storage_path: data/memory.json
  debounce_seconds: 30         # 防抖间隔
  max_facts: 100
  max_injection_tokens: 2000   # 注入记忆的 token 上限

title:
  enabled: true
  max_chars: 60

server:
  host: 127.0.0.1
  port: 18900
```

### 6.2 模型工厂机制

`use: langchain_openai:ChatOpenAI` 的解析流程:
1. `models/factory.py` 中 `resolve_class("langchain_openai:ChatOpenAI")`
2. `importlib.import_module("langchain_openai")` → `getattr(module, "ChatOpenAI")`
3. 用 config 中的参数实例化: `ChatOpenAI(model=..., api_key=..., base_url=...)`

支持任意 LangChain 兼容模型，只需在 config.yaml 中指定正确的 `use:` 类路径。

### 6.3 环境变量

`config/app_config.py` 中，值以 `$` 开头的字段会自动解析为 `os.getenv()`:
- `$DEEPSEEK_API_KEY` → `os.getenv("DEEPSEEK_API_KEY")`
- 存放在 `backend/.env`（python-dotenv 加载）

---

## 7. 记忆系统

### 7.1 存储格式 (data/memory.json)

```json
{
  "user": {
    "name": "",
    "preferences": ""
  },
  "history": {
    "recent_topics": [],
    "interaction_count": 0
  },
  "facts": [
    {
      "category": "brand",
      "content": "用户品牌定位中高端，目标客群25-35岁女性",
      "created_at": "2025-03-24T06:35:00Z"
    }
  ]
}
```

### 7.2 生命周期

```
[注入] 每次 LLM 调用前:
  MemoryMiddleware.before_model
    → 读取 memory.json
    → format_memory_for_injection() 格式化（≤2000 tokens）
    → 注入为 SystemMessage("<memory>...</memory>")

[提取] 每轮对话后:
  MemoryMiddleware.after_agent
    → 将对话入队 MemoryUpdateQueue
    → 30秒防抖（避免频繁写入）
    → update_memory_from_conversation()
      → LLM 分析对话，提取新 facts
      → _apply_updates() 合并到 memory.json（去重）

[刷新] 应用关闭时:
  lifespan shutdown hook
    → MemoryUpdateQueue.flush()  确保所有待写入的记忆保存
```

---

## 8. API 端点

| 方法 | 路径 | 功能 | 请求体 |
|------|------|------|--------|
| GET | /health | 健康检查 | - |
| POST | /api/chat | 发送消息 | `{ session_id, message, model_name?, stream? }` |
| GET | /api/models | 可用模型列表 | - |
| GET | /api/agents | 部门 Agent 列表 | - |
| GET | /api/memory | 查看记忆 | - |
| PUT | /api/memory | 修改记忆 | `{ user, history, facts }` |

### /api/chat 响应格式

```json
{
  "ok": true,
  "message": {
    "id": "uuid",
    "role": "assistant",
    "content": "综合回答文本...",
    "createdAt": "ISO8601"
  },
  "title": "自动生成的标题（首轮对话后）",
  "department_results": null
}
```

---

## 9. 前端架构

### 9.1 核心 State

```javascript
sessions:  [{ id, title, updatedAt, messages: [{id, role, content, createdAt}], uploads }]
agents:    [{ id, name, desc, enabled, instructions, isDefault, binding }]  // 6个
profiles:  [{ id, name, provider, baseUrl, apiKey, model }]
theme:     'win98' | 'mac'
```

### 9.2 IPC 通信（preload.js → boxccAPI）

| 方法 | IPC channel | 方向 |
|------|-------------|------|
| sendChat(payload) | chat:send | → Python 后端 |
| loadState() | app-state:load | → Node.js stateService |
| saveState(data) | app-state:save | → Node.js stateService |
| listSessions() | sessions:list | → Node.js sessionService |
| saveSessions(data) | sessions:save | → Node.js sessionService |
| createSession(data) | sessions:create | → Node.js sessionService |
| listProfiles() | profiles:list | → Node.js profileRegistryService |
| saveProfiles(data) | profiles:save | → Node.js profileRegistryService |
| listAgents() | agents:list | → Node.js agentService |
| saveAgents(data) | agents:save | → Node.js agentService |

### 9.3 状态持久化

- 前端 state 变化 → 120ms 防抖 → `boxccAPI.saveState({ sessions, agents, profiles })`
- 写入 `data/state.json`
- 启动时 `boxccAPI.loadState()` 恢复

---

## 10. 关键设计决策

1. **Electron + Python 混合架构**: 前端状态管理留在 Node.js（快速、同步），AI 推理放在 Python（生态丰富）
2. **orc 不是独立子 Agent**: Lead Agent 自身就是主席团，减少一层调用开销
3. **强制全部门执行**: 所有 enabled 部门必须被调用，主席团可分配"无需行动"但不能跳过
4. **风控部串行**: crt 必须在所有工作部门完成后才运行，看到全貌才能审查
5. **中间件管道精简**: 从 DeerFlow 的 12 个精简到 5 个，砍掉沙盒、上传、图片等不需要的
6. **配置驱动**: 部门增删、模型切换、记忆开关都在 config.yaml，无需改代码
7. **模型工厂动态加载**: `use: module:Class` 支持任意 LangChain 兼容模型

---

## 11. 依赖关系

### Python (pyproject.toml)
```
fastapi, uvicorn[standard], pydantic, pyyaml, python-dotenv,
langchain-core, langchain, langchain-openai, langchain-anthropic,
langgraph, langgraph-checkpoint-sqlite, httpx
```

### Node.js (package.json)
```
electron (主框架)
```

---

## 12. 开发/运行方式

```bash
# 1. 安装 Python 依赖
cd backend && pip install -e .

# 2. 配置环境变量
cp .env.example .env  # 填入 API Keys

# 3. 单独启动 Python 后端（开发调试）
cd backend && python -m app.main
# → http://127.0.0.1:18900/health

# 4. 启动完整应用
cd workbench-app && npx electron .
# → Electron 自动启动 Python 子进程
```

---

## 13. 已知限制与后续方向

### 当前限制
- 前端是单文件 index.html，Babel 浏览器编译，不适合大规模开发
- 没有用户认证（桌面单用户场景不需要）
- 记忆系统使用 JSON 文件，不支持多用户/并发写入
- SSE 流式输出已实现后端，但前端尚未接入

### 后续可扩展
- 前端接入 SSE 流式显示（逐字输出）
- 增加 GuardrailMiddleware（服装领域防护）
- 支持文件上传传递给 Agent（当前仅前端展示）
- Agent 绑定不同 Profile（当前绑定 UI 已有但未接通后端）
- 多轮 Agent 交互（当前每个部门只做一轮）
