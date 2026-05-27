# boxcc 1.0

`boxcc` 是一个基于 Electron + Python 后端的服装企划多智能体工作台。  
当前版本重点支持主席团编排、部门协作、质检复核、执行清单和思考过程展示。

## 项目结构

- `index.html`：桌面端主界面
- `main.js` / `preload.js`：Electron 主进程与桥接
- `main/`：主进程服务
- `backend/`：FastAPI + LangGraph 多智能体后端

## 运行环境

- Node.js 18+
- Python 3.11+
- macOS / Windows 均可运行

macOS 用户如果通过 Homebrew 安装 Python，推荐：

```bash
brew install node python@3.12
```

## 安装

### 1. 安装前端依赖

项目根目录执行：

```bash
npm install
```

### 2. 安装后端依赖

进入 `backend` 目录后安装：

```bash
cd backend
python3 -m pip install -e .
```

macOS/Homebrew Python 推荐使用项目虚拟环境，避免 PEP 668 的系统 Python 限制：

```bash
npm run backend:install
```

如果只想用普通安装方式，也可以：

```bash
cd backend
python3 -m pip install fastapi "uvicorn[standard]" pydantic pyyaml python-dotenv langchain-core langchain-openai langchain-anthropic langgraph langgraph-checkpoint-sqlite httpx
```

### 3. 配置模型

项目默认通过环境变量读取 API Key。可参考：

- [backend/.env.example](backend/.env.example)
- [backend/config.yaml](backend/config.yaml)

常见做法：

```bash
export DEEPSEEK_API_KEY="your_api_key"
```

也可以在应用前端里直接填写 `API Key` 和 `Base URL`。

## 启动

在项目根目录执行：

```bash
npm start
```

Electron 会启动桌面窗口，并自动拉起 Python 后端。

macOS 下 Electron 会自动查找 Python 3.11+，查找顺序包含：

- 项目内 `.venv`
- `BOXCC_PYTHON` 环境变量
- `/opt/homebrew/bin/python3`
- `/opt/homebrew/opt/python@3.12/bin/python3.12`
- `/usr/local/bin/python3`
- `/usr/local/opt/python@3.12/bin/python3.12`
- `python3` / `python`

如果你安装了多个 Python 版本，可以显式指定：

```bash
export BOXCC_PYTHON="/opt/homebrew/bin/python3"
npm start
```

## macOS 打包

安装依赖后执行：

```bash
npm run dist
```

产物会输出到 `dist/`。当前版本仍依赖本机 Python 3.11+ 和后端依赖，请先执行 `python3 -m pip install -e ./backend`。

## 基本使用

1. 打开右侧 `Personal Settings`
2. 选择模型提供商
3. 填写 `API Key` / `Base URL`
4. 选择模型
5. 在聊天框输入任务

当前支持的核心体验：

- 主席团 (`orc`) 自动从 18 个垂直 specialist agent 的注册表中挑选合适的协作组合
- 注册表 + flat catalog 架构 —— 加新 agent 只需 yaml 改一行 + 写一份 spec.md（无需改 Python）
- 风控部 (`crt`) 统一做跨域验证与返工指向
- KB（知识库）三层授权：系统注册 ∩ agent 声明范围 ∩ 本次任务授权
- delegate workflow 由 LangGraph StateGraph 编排（动态 Send fan-out + critic + 可选 rework 回路）
- 聊天框内显示思考过程与执行清单
- 同一会话内保留主席团状态与 worker shard

详见 [`doc/handoff-stategraph-and-kb.md`](doc/handoff-stategraph-and-kb.md)。

## 注意事项

- 不要把真实 API Key、日志和本地会话数据提交到 Git
- `.gitignore` 已经排除了常见依赖、日志和本地状态文件
- `dist/` 是 Electron 构建产物，重新打包时会全部重新生成；包内残留的旧 agentspec 文件不影响源码

## 仓库地址

如果你的 GitHub 仓库页面是：

`https://github.com/zr15504328511-debug/boxcc1.0`

那么对应的 Git 远程地址通常是：

```text
https://github.com/zr15504328511-debug/boxcc1.0.git
```
