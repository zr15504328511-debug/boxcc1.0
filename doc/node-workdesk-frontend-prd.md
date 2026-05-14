# boxcc 节点式工作桌面前端 PRD

版本：Draft 0.1  
日期：2026-05-05  
用途：交给前端/agent 构建团队作为产品方向、约束和验收依据。本文不是像素级设计稿，也不锁死具体技术实现。

## 1. 背景

boxcc 当前已经具备多 Agent 后端雏形：`orc` 负责路由和任务拆解，worker 部门负责专业输出，`crt` 负责质检和返工判断。但现有前端仍以传统聊天框为中心，无法充分表达多 Agent 系统中的任务包、部门节点、流式过程、质检关系和最终企划产物。

下一阶段前端应从“聊天应用”转向“节点式工作桌面”。用户不需要手工搭建工作流，而是观察、理解、检查和复用由 `orc` 编排出来的多 Agent 任务执行图。

## 2. 产品目标

### 核心目标

- 将一次多 Agent 任务执行过程可视化为节点图。
- 明确展示 `orc` 如何把任务传导给各 worker。
- 每个节点可查看任务包、流式输出、过程摘要、质检状态。
- 保留原有能力：模型配置、会话、Agent 展示、发送任务、查看结果。
- 为未来产出长页企划书、PPT、表格、素材包等 artifact 留出空间。

### 用户感受目标

用户应感觉自己在使用一个“虚拟工作桌面”，而不是普通网页聊天框。  
这个桌面里有多部门节点、任务流、结果文档、设置面板和运行状态。

## 3. 非目标

MVP 阶段不做以下能力：

- 不做用户自由连线。
- 不做 n8n / Dify 风格的通用 workflow editor。
- 不做完整 PPT 编辑器。
- 不重写模型配置的底层存储逻辑。
- 不做复杂权限系统。
- 不展示真实 chain-of-thought。
- 不要求一次性重构全部后端事件协议。

允许前端先从现有 API/SSE 事件推导节点图，后续再推动后端补统一 `run_graph` 数据结构。

## 4. 核心设计原则

### 4.1 编排权属于 orc

用户不能随意把节点连起来。  
节点和边来自后端运行结果或流式事件。

用户可以：

- 拖动节点位置。
- 展开/折叠节点。
- 查看节点详情。
- 复制任务包或输出。
- 重新运行任务。
- 后续阶段可选择“要求返工”或“继续生成产物”。

用户不可以：

- 手动画 worker 之间的执行边。
- 绕过 `orc` 直接指定内部链路。
- 修改已完成 run 的历史事实。

### 4.2 节点图是执行视图，不是流程编辑器

节点图表达“这次任务发生了什么”。  
它可以保存布局，但不代表用户创建了一个永久工作流。

### 4.3 思考链展示为可审计摘要

前端不应展示模型真实隐藏思考链。  
应展示：

- 路由依据摘要
- 任务拆解理由
- checklist
- worker 执行摘要
- critic 质检依据
- 风险和未解决项

可命名为“思考过程”“决策摘要”“执行依据”，但实现上应避免暴露原始 chain-of-thought。

### 4.4 面向长页企划书/PPT 扩展

每个 worker 输出不是孤立聊天文本，而是未来企划书或 PPT 的素材来源。  
前端信息结构应为 artifact 做准备：

- 章节
- 页面
- 表格
- 卖点
- 风险项
- 图文素材
- 质检意见

## 5. 目标用户流程

### 5.1 基础任务流程

1. 用户进入 boxcc 工作桌面。
2. 用户在任务输入区描述需求。
3. `orc` 节点出现，显示“正在分析任务”。
4. `orc` 根据 routing policy 生成 worker 节点。
5. 画布出现从 `orc` 指向 worker 的连线动画。
6. 每个 worker 节点开始流式输出状态和内容。
7. worker 完成后，输出汇入 `crt` 质检节点。
8. `crt` 节点显示通过、需修正或失败。
9. 如有返工，出现从 `crt` 指向对应 worker 的返工边。
10. 最终汇入 Final / Artifact 节点。
11. 用户在产物区查看最终方案。

### 5.2 用户点击节点

点击任一节点，应打开详情面板或节点内展开视图：

- 节点身份
- 当前状态
- 输入任务包
- 流式输出
- 过程摘要
- 结果内容
- 质检意见
- 与其他节点的关系

## 6. 信息架构

建议主界面分为 4 个区域，但具体布局可由设计团队调整。

### 6.1 Desktop Shell

虚拟工作桌面外壳。

应包含：

- 当前项目/会话名
- 后端运行状态
- 当前模型配置入口
- 任务运行状态
- 设置入口
- 可选：类似任务栏或侧边 dock

### 6.2 Run Graph Canvas

核心节点画布。

能力：

- 节点可拖动。
- 支持缩放和平移。
- 节点间边由系统生成。
- 边可展示执行方向和动画。
- 当前运行中的边有流动效果。
- 支持自动布局，但允许用户手动整理。

### 6.3 Node Inspector

节点详情区域。

可做成：

- 右侧检查器
- 浮动窗口
- 节点展开面板

不强制实现形式，但必须保证节点详情足够清晰。

### 6.4 Artifact Preview

最终产物预览区。

MVP 可先支持 Markdown 长页预览。  
后续可支持：

- PPT 大纲
- 表格
- 图片参考
- 可导出文档

## 7. 节点模型

MVP 至少支持以下节点类型。

### 7.1 User Request Node

表示用户原始任务。

字段建议：

- `node_id`
- `type: user_request`
- `title`
- `content`
- `created_at`

### 7.2 ORC Node

表示主席团 / leader。

展示内容：

- 路由分类
- selected workers
- checklist
- routing policy
- 任务拆分摘要

状态：

- idle
- analyzing
- dispatching
- waiting
- finalizing
- failed

### 7.3 Worker Node

表示部门 worker。

展示内容：

- worker id
- worker name
- task packet
- available skill packs
- streaming output
- latest output
- retry count
- validation feedback

状态：

- pending
- running
- completed
- needs_rework
- reworking
- validated
- failed
- timed_out

### 7.4 Critic Node

表示质检部。

展示内容：

- pass gate
- summary
- rework targets
- risk findings
- second review result

状态：

- pending
- reviewing
- passed
- fixes_required
- failed

### 7.5 Final / Artifact Node

表示最终交付。

展示内容：

- final answer
- validation gate
- linked artifacts
- unresolved issues

MVP 可先展示 Markdown 方案。  
后续扩展为长页企划书或 PPT artifact。

## 8. 边模型

MVP 边不支持用户编辑，只展示系统关系。

建议边类型：

- `user_to_orc`
- `task_packet`
- `worker_output`
- `validation`
- `rework`
- `finalize`

边应至少有：

- source node
- target node
- type
- status
- label

运行中的边可展示流动动画。  
已完成边可静态显示。  
失败边可用风险色或虚线。

## 9. 流式输出要求

每个节点需要能接收和展示流式过程。

### 9.1 MVP 可用数据源

当前后端已有：

- `run_step`
- `checklist_sync`
- `answer_delta`
- `department_results`
- `workflow_artifact`

MVP 可以基于这些事件推导节点状态。

### 9.2 推荐后续事件模型

后续建议后端补充统一事件：

```json
{
  "type": "graph_event",
  "run_id": "string",
  "node_id": "string",
  "node_type": "orc|worker|critic|artifact",
  "event": "created|started|delta|completed|failed|edge_created",
  "payload": {}
}
```

此项不是 MVP 阻塞项。

## 10. 任务包展示

Worker 节点必须能查看 `task_packet`。

任务包建议展示：

- objective
- task
- context
- constraints
- required_output
- requested_skill_packs
- success_criteria
- notes

展示形式可以是结构化表单、折叠 JSON、或格式化卡片。  
不建议只展示原始大段 JSON。

## 11. 原功能保留策略

### 11.1 模型配置

必须保留：

- provider 选择
- base URL
- API Key
- model 选择
- 刷新模型列表

MVP 可以保留现有逻辑，只改变入口和展示位置。

建议迁移到：

- 设置窗口
- 控制面板
- 右侧系统设置抽屉

### 11.2 会话功能

必须保留：

- 创建会话
- 切换会话
- 查看历史消息或历史 run

但主体验应从“聊天消息列表”转向“任务运行图 + 产物”。

### 11.3 Agent 展示

必须保留：

- 部门列表
- worker 名称
- worker 描述
- 当前启用状态

后续可以扩展为“部门资源管理器”。

## 12. MVP 验收标准

### 必须满足

- 用户可以输入任务并运行。
- 非直答任务能看到 `orc -> worker -> critic -> final` 的节点结构。
- 节点可拖动。
- 用户不能自由创建连线。
- worker 节点能看到任务包。
- worker 节点能看到输出。
- critic 节点能看到质检结论。
- 原模型配置能力可用。
- 直答任务可以退化为 `user -> orc -> final` 简图。
- 当前运行失败时，节点图能显示失败状态，而不是只在聊天框报错。

### 应该满足

- 边有方向和基础动画。
- 节点支持展开/折叠。
- 最终结果在 Artifact Preview 中展示。
- 会话切换后可恢复最近一次 run 的节点图。

### 可以暂缓

- 自动美观布局的高级算法。
- 多 run 时间线。
- PPT 真正导出。
- 复杂 artifact 编辑。
- 用户自定义 worker。
- 用户手动连线。

## 13. 可扩展方向

### 13.1 长页企划书

未来 Final / Artifact 节点可以生成长页企划书，章节包括：

- 项目背景
- 目标客群
- 风格定位
- SKU 结构
- 波段与上新节奏
- 面料和工艺风险
- 成本与定价
- 卖点文案
- 质检结论
- 返工记录

### 13.2 PPT

未来可将企划书章节映射为 PPT 页面：

- 封面
- 核心结论
- 市场洞察
- 产品结构
- 关键款说明
- 成本测算
- 风险控制
- 上市节奏
- 质检结论

### 13.3 返工 target

后续可将 critic 输出升级为结构化 target：

- target id
- owner
- severity
- linked artifact section
- required fix
- acceptance criteria
- status

MVP 不强制实现，但前端节点模型应预留 rework target 展示区域。

### 13.4 Run Replay

未来支持回放一次任务执行：

- orc 分析
- worker 启动
- 输出流动
- critic 审查
- 返工
- final 生成

## 14. 给构建团队的实现建议

以下建议不锁死技术选型。

- 可考虑使用 React Flow / XYFlow 一类画布库。
- 优先把数据模型梳理清楚，再做视觉打磨。
- 第一版不要做自由 workflow editor。
- 节点样式应克制、清晰，优先可读性。
- 视觉可以有“虚拟桌面”气质，但不要牺牲信息密度。
- 任务包和输出内容会很长，必须考虑滚动、折叠和复制。
- 流式事件可能乱序或缺失，前端需要有容错。
- 后端字段不稳定时，前端需要适配层，不要让 UI 组件直接依赖原始 API。

## 15. 需要后端配合但不阻塞 MVP 的事项

- 提供统一 `run_id`。
- 提供显式 `node_id`。
- 提供 `graph_event` SSE。
- 提供最终 `run_graph` artifact。
- 将 routing policy 作为显式 artifact 返回。
- 将 critic rework target 结构化。
- 将 artifact section 与 worker output 建立引用关系。

## 16. 初版成功标准

初版不追求复杂，而追求方向正确。

当用户运行一个完整企划任务时，应能清楚看到：

1. 用户任务进入 `orc`。
2. `orc` 选择了哪些部门。
3. 每个部门拿到了什么任务包。
4. 每个部门正在输出什么。
5. 质检如何判断结果。
6. 最终方案从哪些节点汇总而来。

如果这 6 件事清楚，MVP 就是成功的。
