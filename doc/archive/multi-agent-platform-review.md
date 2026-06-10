# boxcc 多 Agent 平台真实任务评估与问题记录

评估日期：2026-05-03  
评估对象：`boxcc 1.0` Electron + FastAPI + LangGraph 多智能体工作台  
评估方式：使用 DashScope OpenAI-compatible 接口与 `deepseek-v4-flash` 做真实请求测试；API Key 仅作为临时环境变量使用，未写入项目文件。

## 一、真实任务测试记录

### 任务设计

本次选择一个能覆盖多部门协作的真实业务任务：

> 对「2026夏季都市通勤女装胶囊系列」做完整上市会审，输出 SKU 结构、面料/工艺质量风险、成本定价注意点、详情页核心卖点，并由质检视角判断是否建议进入打样。

该任务天然需要：

- `pln` 企划部：SKU 结构与上市节奏
- `dom` 学术部：面料、工艺、质量风险
- `ana` 经营部：成本、价格带、毛利与预算可行性
- `cpy` 宣传部：详情页卖点与表达
- `crt` 质检部：复核冲突、遗漏和交付风险

### 实测结果

- 后端接口：`POST /api/chat`
- 返回状态：`200 OK`
- 总耗时：约 `211.15s`
- 路由分类：`integrated_review`
- 选中 worker：`["dom", "pln", "ana", "cpy"]`
- 部门结果数：`10`
- 执行链路：4 个 worker 初稿 + 质检 + 4 个 worker 返工 + 二次质检
- 最终质检门禁：`fixes_required`

### 平台表现判断

正向表现：

- 能识别完整方案会审属于 `integrated_review`。
- 能一次性启用 4 个 worker，并自动进入质检。
- 质检能发现跨部门冲突：如面料结论与卖点验证未闭环、成本分析被截断、打样策略表述矛盾。
- 能触发返工链路，说明平台已经具备「worker -> critic -> rework -> critic」的核心骨架。

暴露问题：

- 总耗时超过 3 分钟，对桌面端交互偏长。
- 二次质检后仍为 `fixes_required`，最终答案却仍生成给用户，交付门禁不够硬。
- 最终回答中保留了较多内部部门痕迹，像平台执行摘要，而不是面向用户的成熟业务交付。
- 返工后仍存在未完全解决的问题，说明返工目标跟踪不够结构化。

## 二、多 Agent 平台维度评分

| 维度 | 评分 | 说明 |
| --- | ---: | --- |
| 任务路由能力 | 7.0/10 | 明确「完整会审」时能正确路由，但此前自然复杂请求曾出现只口头说明路由、不实际调用工具的问题。 |
| Worker 任务拆解 | 7.0/10 | 能给不同部门生成任务包，但任务包质量依赖主模型稳定性，缺少后端确定性校验。 |
| 并行执行能力 | 7.5/10 | worker 能并行执行，并受 `max_concurrent` 控制；真实任务中链路完整。 |
| Critic 质检能力 | 8.0/10 | 质检能抓住跨部门冲突和卖点真实性风险，是当前平台最亮的部分。 |
| 返工闭环 | 5.5/10 | 能触发返工，但二次质检仍未通过时缺少硬性拦截和继续修复策略。 |
| 状态与可追踪性 | 6.5/10 | 有 checklist、department_results、workflow_artifact，但事件标题中存在乱码/问号，观测体验受损。 |
| 延迟与成本控制 | 4.5/10 | 一次完整任务 211 秒，10 次模型调用左右，成本和等待时间偏高。 |
| 模型/供应商适配 | 6.5/10 | OpenAI-compatible 路径可用；但不同模型的 tool calling 稳定性需要自动验证。 |
| 前端产品体验 | 5.5/10 | 能展示过程，但生产构建、CSP、CDN/Babel 警告明显，离发布还有距离。 |
| 安全与隐私 | 4.0/10 | CORS 全开放、API Key 明文保存，是平台级风险。 |
| 测试与发布准备 | 4.0/10 | 缺少自动化测试；`pytest` 未安装；`npm audit` 有 high 漏洞。 |

综合评分：**6.1/10**

定位判断：当前是一个「多 Agent 原型已经跑通、但还没有形成稳定产品门禁」的版本。

## 三、关键问题记录

### P0：非直答任务未强制进入工具链路

现象：

- 明确完整会审任务能触发工具调用。
- 但此前自然复杂任务出现过模型只输出「我将启用哪些部门」，没有真正调用 `delegate_to_departments`，返回 `department_count=0`。

影响：

- 用户以为平台做了多部门协作，实际只是主模型单独回答。
- 多 Agent 平台的核心价值会被削弱。

建议修补：

- 在 `/api/chat` 后端增加确定性门禁：对用户问题先跑 `_build_routing_policy()`。
- 如果路由不是 `direct_answer`，但最终没有 `workflow_artifact.department_results`，则判定为 orchestration failure。
- 可自动二次调用，追加系统约束：「本轮必须调用 `delegate_to_departments`，不得只描述计划」。
- 二次仍失败时，返回明确错误，而不是把伪协作答案交给用户。

### P0：质检不通过仍然交付最终答案

现象：

- 本次真实任务二次质检结果为 `fixes_required`。
- 平台仍生成了最终答案，并把质检发现的问题一起交付。

影响：

- 用户收到的是「带缺陷的方案」，而不是平台承诺的质检闭环结果。
- 质检门禁目前更像提示，不像真正 gate。

建议修补：

- 将 `validation_report.pass_gate` 纳入最终输出策略。
- `passed`：正常交付。
- `warnings`：交付但显式标记风险。
- `fixes_required`：默认不交付最终业务方案，而是返回「需要补齐的信息/正在继续返工/建议用户确认」。
- 增加最大返工轮次，例如 `max_rework_rounds=2`，并把未解决项结构化传回 UI。

### P1：返工目标没有结构化验收

现象：

- critic 给出了明确 rework targets，但返工后仍存在 ana 截断、dom/cpy 验证未闭环等问题。

影响：

- 返工只是再生成一次，并未逐项验证「每个 target 是否关闭」。

建议修补：

- 给每个 rework target 分配稳定 ID。
- worker 返工输出必须包含 `resolved_target_ids` 和 `remaining_risks`。
- critic 二次复核时逐项判定 `open/resolved/partially_resolved`。
- UI 中展示未关闭项，而不是只展示部门长文本。

### P1：耗时过长，缺少分层执行策略

现象：

- 完整任务耗时约 211 秒。
- 初稿 4 worker + critic + 返工 4 worker + critic，调用链路很重。

影响：

- 桌面用户等待成本高。
- 模型费用和失败概率随链路长度显著增加。

建议修补：

- 支持「轻量模式 / 标准模式 / 深度会审模式」。
- 默认最多 2-3 个 worker；只有用户明确选择深度会审才启用 4 worker。
- critic 只要求问题部门返工，不要默认所有 worker 都返工。
- 对 worker 输出设置更严格的 token 上限和结构化摘要。

### P1：事件标题和部分中文显示存在乱码/问号

现象：

- `subagents/tools.py` 中多个 `emit_run_step` title/summary 出现 `????????`。

影响：

- 思考过程与执行清单可读性下降。
- 调试和用户信任感受损。

建议修补：

- 全量清理 `tools.py`、`tools_live.py`、`executor.py` 中的乱码文案。
- 增加一个快照测试，确保运行事件标题不包含 `?{3,}`。

### P1：安全边界偏弱

现象：

- 后端 CORS 为 `allow_origins=["*"]`。
- API Key 通过 profile 明文保存。
- Electron renderer 没有严格 CSP，日志出现 Insecure Content-Security-Policy 警告。

影响：

- 本机恶意网页或注入脚本可能调用本地后端。
- 用户模型密钥泄露风险高。

建议修补：

- 后端启动时生成随机 local auth token，Electron 主进程调用后端时带 token。
- CORS 限制为 localhost/file origin，并校验 token。
- API Key 使用 Electron `safeStorage` 或系统钥匙串保存。
- 迁出 CDN React/Babel/Tailwind，改为本地构建并设置 CSP。

### P2：测试体系缺失

现象：

- `python -m compileall` 通过。
- `node --check` 通过。
- `pip check` 通过。
- `pytest` 未安装，仓库未发现测试文件。
- `npm audit` 有 13 个漏洞，其中 8 个 high。

影响：

- 多 agent 路由、返工、质检门禁等核心行为没有回归保障。

建议修补：

- 增加 `pytest` dev 依赖安装说明和最小测试集。
- 测试覆盖：
  - direct answer 不调用 worker。
  - planning/quality/mixed/integrated_review 正确路由。
  - 非 direct_answer 若无 department_results 则失败。
  - `fixes_required` 不应被当作正常最终交付。
  - event title 不应含乱码。
- 升级 Electron / electron-builder 后跑 smoke test。

## 四、优化路线图

### 第一阶段：让平台「不伪协作」

目标：复杂任务必须产生真实部门结果。

建议改动：

- 后端增加 routing precheck。
- 增加 no-tool-call failure 检测。
- 对自然复杂请求做自动二次 orchestration retry。
- UI 明确展示「本轮是否真实调用部门」。

验收标准：

- 10 个复杂任务样例中，至少 9 个产生 department_results。
- 用户最终答案不得出现「我将调用部门」但 artifact 为空的情况。

### 第二阶段：让质检成为真正门禁

目标：critic 不通过时不直接交付缺陷方案。

建议改动：

- `pass_gate` 驱动最终响应策略。
- rework target ID 化。
- 二次质检仍不通过时，输出「未关闭问题清单」而非伪最终方案。

验收标准：

- `fixes_required` 时 UI 和 API 都能明确标识未通过。
- 每个 rework target 都有 open/resolved 状态。

### 第三阶段：降低等待与成本

目标：常见任务 30-90 秒内完成，深度会审可接受更长时间。

建议改动：

- 增加 execution mode。
- 只返工被 critic 点名的部门。
- worker 输出强制结构化和长度限制。
- 对长任务支持流式阶段结果与用户中止。

验收标准：

- 标准 mixed 任务 <= 90 秒。
- direct answer <= 5 秒。
- integrated_review 清楚显示预计耗时和进度。

### 第四阶段：补安全与发布质量

目标：从内测原型提升到可分发桌面应用。

建议改动：

- 本地后端 token。
- safeStorage 保存密钥。
- Vite/React/Tailwind 本地构建。
- CSP。
- 依赖漏洞升级。
- 最小自动化测试和打包 smoke test。

验收标准：

- Electron 不再输出 CSP/CDN/Babel 生产警告。
- `npm audit --audit-level=high` 无 high 漏洞，或有明确例外说明。
- README 给出安全配置与故障排查。

## 五、建议后的目标评分

如果完成 P0 + P1 修补，预期评分可提升为：

| 维度 | 当前 | 修补后目标 |
| --- | ---: | ---: |
| 任务路由能力 | 7.0 | 8.5 |
| 返工闭环 | 5.5 | 8.0 |
| 状态与可追踪性 | 6.5 | 8.0 |
| 延迟与成本控制 | 4.5 | 7.0 |
| 安全与隐私 | 4.0 | 8.0 |
| 测试与发布准备 | 4.0 | 7.5 |

综合目标：**8.0/10**

## 六、结论

boxcc 的多 Agent 骨架是成立的：真实任务中能完成路由、并行 worker、质检、返工、二次质检，说明平台核心方向正确。

当前最大短板不是「能不能跑」，而是「能不能稳定、可信、可交付」。优先级最高的是两件事：

1. 复杂任务必须强制产生真实部门协作结果，避免伪协作。
2. 质检不通过时必须成为真正门禁，避免把带缺陷方案包装成最终答案。

完成这两项后，再处理延迟、安全、测试和前端生产化，项目会从可演示原型进入可认真内测的阶段。
