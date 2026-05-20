# boxcc 1.0

`boxcc` 是一个面向服装企划场景的多智能体桌面工作台。当前分支以“节点式工作桌面”为主体验：用户把任务交给 `orc` 主席团，系统会自动分发给专业部门，汇总 worker 输出，并由质检部复核后生成最终交付。

## 当前状态

当前代码基于 Electron + Vite/React + Python FastAPI：

- Electron 主进程负责窗口、IPC、本地状态、自动拉起 Python 后端。
- React 渲染一个可拖动、可展开的桌面式工作台。
- Python 后端负责 LangGraph/LangChain 多智能体编排。
- 前端通过 SSE 接收运行事件，把执行过程映射成节点、书签状态、扫光流转和节点详情。

## 核心体验

- `orc` 主席团理解任务、选择部门、分发任务包。
- `dom` 学术部负责面料、工艺、版型等专业判断。
- `pln` 企划部负责 SKU、系列结构、波段和排期。
- `ana` 经营部负责价格、成本、毛利和经营分析。
- `cpy` 宣传部负责卖点提炼、传播表达和文案。
- `crt` 质检部负责冲突检查、风险复核和返工意见。
- 右侧书签条展示 agent 激活、运行、完成状态。
- 节点详情窗口展示决策依据、任务包、输出、质检和最终结果。
- 模型、部门、会话和产物文件夹都以桌面浮窗形式打开。

## 技术栈

- 桌面壳：Electron 31
- 前端：React 18、Vite、TypeScript、Tailwind CSS、Zustand
- 后端：Python 3.11+、FastAPI、LangChain、LangGraph
- 模型提供商：OpenAI、Anthropic、OpenRouter、Custom，以及后端配置中的 DeepSeek
- 持久化：Electron userData 下的 JSON 文件；后端会话/检查点数据写入后端数据目录

## 目录结构

```text
.
├── main.js                     # Electron 主进程，启动窗口和 Python 后端
├── preload.js                  # contextBridge，向前端暴露 boxccAPI
├── main/                       # Electron 本地状态、profile、agent 服务
├── renderer/                   # Vite + React 前端
│   └── src/
│       ├── desktop/            # 节点式桌面、书签条、浮窗、模型/部门/会话面板
│       ├── adapter/            # 后端 SSE 事件 -> RunGraph
│       ├── inspector/          # 任务包、质检、产物预览组件
│       ├── store/              # Zustand 会话状态与 IPC 桥接
│       └── theme/              # 桌面样式与 agent 色彩 token
├── backend/                    # Python FastAPI + 多智能体后端
│   ├── app/routers/            # chat、models、agents、health 等 API
│   ├── agents/                 # 主 agent、prompt、中间件
│   ├── agentspecs/             # orc/dom/pln/ana/cpy/crt 角色说明
│   ├── subagents/              # 部门执行器、任务包、delegate 工具
│   ├── session/                # 执行清单、worker shard、会话状态
│   └── config.yaml             # 后端模型、部门、memory、checkpointer 配置
└── package.json                # npm 脚本与 Electron Builder 配置
```

## 环境要求

- Node.js 18+
- Python 3.11+，推荐 Python 3.12
- macOS 或 Windows

macOS 可用 Homebrew 安装：

```bash
brew install node python@3.12
```

## 安装

安装 Node 依赖：

```bash
npm install
```

安装 Python 后端依赖，推荐使用项目内虚拟环境：

```bash
npm run backend:install
```

如果不用脚本，也可以手动安装：

```bash
python3 -m pip install -e ./backend
```

## 模型配置

应用内可以在“模型”浮窗里创建 profile，填写：

- Provider
- Base URL
- API Key
- Model

后端也支持从环境变量读取默认模型配置。可参考：

- `backend/.env.example`
- `backend/config.yaml`

示例：

```bash
export DEEPSEEK_API_KEY="your_api_key"
```

如果本机有多个 Python，可以显式指定 Electron 使用的 Python：

```bash
export BOXCC_PYTHON="/opt/homebrew/bin/python3.12"
```

## 启动

开发模式，前端走 Vite 热更新，Electron 自动加载 Vite 地址：

```bash
npm run dev
```

普通桌面启动：

```bash
npm start
```

`npm start` 会加载 `dist/renderer/index.html`。如果本地还没有构建产物，请先执行：

```bash
npm run renderer:build
npm start
```

Electron 启动时会自动：

1. 查找 Python 3.11+。
2. 启动 `backend/app/main.py`。
3. 等待 `http://127.0.0.1:18900/health` 健康检查通过。
4. 创建桌面窗口。

## 常用脚本

```bash
npm run dev              # Vite + Electron 开发模式
npm run renderer:build   # 构建前端到 dist/renderer
npm start                # 启动 Electron 桌面应用
npm run backend:install  # 创建 .venv 并安装后端
npm run pack             # 本地目录打包
npm run dist             # 生成安装包
```

## 使用方式

1. 启动应用。
2. 如果没有模型 profile，应用会自动打开“模型”浮窗。
3. 配置 provider、base URL、API key 和模型名。
4. 在左下角输入任务并发送给 `orc`。
5. 观察右侧书签条的 agent 状态变化。
6. 点击已激活的书签，打开对应节点详情。
7. 在“会话”“部门”“产物文件夹”等浮窗中管理运行上下文。

## 后端事件与前端图谱

后端会通过 chat stream 发出运行事件，包括：

- `run_step`
- `checklist_sync`
- `node_task_packet`
- `node_output_delta`
- `node_output_done`
- `answer_delta`
- `done`
- `error`

前端 `renderer/src/adapter/graphAdapter.ts` 会把这些事件推导为 `RunGraph`，再驱动桌面书签、节点详情、最终交付和状态动画。

## 打包

构建前端并生成安装包：

```bash
npm run dist
```

Electron Builder 会把 `backend/**`、`main/**`、`dist/renderer/**`、`main.js`、`preload.js` 和 `package.json` 纳入产物。当前版本仍依赖目标机器可用的 Python 3.11+ 以及后端依赖环境。

## 数据和安全

- 不要提交真实 API Key。
- 不要提交 `.env`、日志、缓存、会话数据、`node_modules`、`.venv`。
- `.gitignore` 已排除常见本地文件，包括 `debug.log`、`.env`、`dist/`、`node_modules/` 和 Python 缓存。
- Electron 本地状态默认写入系统 `userData/data`。
- Python 后端数据默认写入 Electron userData 下的 `backend-data`。

## 当前分支

当前主要开发分支：

```text
节点版0505
```

远端仓库：

```text
https://github.com/zr15504328511-debug/boxcc1.0.git
```
