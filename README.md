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
- Windows 环境下运行更稳

## 安装

### 1. 安装前端依赖

项目根目录执行：

```powershell
npm install
```

### 2. 安装后端依赖

进入 `backend` 目录后安装：

```powershell
cd backend
pip install -e .
```

如果只想用普通安装方式，也可以：

```powershell
cd backend
pip install fastapi "uvicorn[standard]" pydantic pyyaml python-dotenv langchain-core langchain-openai langchain-anthropic langgraph langgraph-checkpoint-sqlite httpx
```

### 3. 配置模型

项目默认通过环境变量读取 API Key。可参考：

- [backend/.env.example](D:/myproject/workbench-app/backend/.env.example)
- [backend/config.yaml](D:/myproject/workbench-app/backend/config.yaml)

常见做法：

```powershell
$env:DEEPSEEK_API_KEY="your_api_key"
```

也可以在应用前端里直接填写 `API Key` 和 `Base URL`。

## 启动

在项目根目录执行：

```powershell
npm start
```

Electron 会启动桌面窗口，并自动拉起 Python 后端。

## 基本使用

1. 打开右侧 `Personal Settings`
2. 选择模型提供商
3. 填写 `API Key` / `Base URL`
4. 选择模型
5. 在聊天框输入任务

当前支持的核心体验：

- 主席团自动决定调用哪些部门
- worker 只接收任务单，不直接读取用户原问题
- 质检部统一做验证与返工指向
- 聊天框内显示思考过程与执行清单
- 同一会话内保留主席团状态与 worker shard

## 注意事项

- 不要把真实 API Key、日志和本地会话数据提交到 Git
- `.gitignore` 已经排除了常见依赖、日志和本地状态文件
- 当前仓库仍包含一部分为处理 Windows 文件锁而做的临时 live 模块，后续会继续收口

## 仓库地址

如果你的 GitHub 仓库页面是：

`https://github.com/zr15504328511-debug/boxcc1.0`

那么对应的 Git 远程地址通常是：

```text
https://github.com/zr15504328511-debug/boxcc1.0.git
```
