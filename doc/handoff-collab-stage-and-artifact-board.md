# Handoff: 协作舞台 + 产物看板（前端）

> 前置：读 [node-workdesk-frontend-prd.md](node-workdesk-frontend-prd.md)（节点式工作桌面 PRD，仍有效）。
> 本文档解决 PRD 落地时被跳过的核心部分：**用户必须亲眼看到部门在协同工作**，以及 PRD §6.4 的产物预览升级为**产物看板**。

## 30 秒理解

当前 renderer 的现状：

- **数据层已经做完了**：`adapter/runGraph.ts` 定义了完整的 RunGraph schema（user/orc/worker/critic/artifact 五类节点 + 六类边 + 状态机），`adapter/graphAdapter.ts`（649 行）已经在把后端 `run_step` / `checklist_sync` / `department_results` / `workflow_artifact` 事件流推导成 RunGraph。
- **视图层缺席**：桌面上没有任何东西消费这张图的拓扑。协同过程只通过右侧书签条的点亮 + 扫光暗示，用户看不到"orc 把任务包发给了谁、谁在干活、质检打回了谁"。
- `NodeDetailFolder` / `TaskPacketView` / `CritiqueView` / `StreamingOutputView` 已存在，可直接复用为节点详情。

**要做的就是两个新视图，零后端改动起步**：

```
RunGraph (已有，store 里现成)
   ├──> ① 协作舞台 CollabStage     ← 桌面中央，运行时自动出现
   └──> ② 产物看板 ArtifactBoard   ← OutputsFolder 升级，跨 run 持久
```

## ① 协作舞台（CollabStage）

### 形态

桌面中央的**固定泳道舞台**，不是自由画布（PRD §4.1：编排权属于 orc，用户不连线）。
五段泳道自上而下（或自左向右）：

```
┌─────────────────────────────────────────────────────┐
│  [用户任务卡]                                          │
│      ↓                                               │
│  [orc 主席团卡] ── 路由分类 chip + checklist 进度       │
│      ↓ ↓ ↓ ↓   ← 任务包飞行动画（信封沿边滑动）          │
│  [worker][worker][worker][worker]  ← 并行工位排        │
│      ↘ ↓ ↙                                           │
│  [crt 风控卡] ── pass_gate 徽章                        │
│      ↓ (passed)        ↺ (fixes_required 红色回流边)   │
│  [producer/产物卡] → 落盘文件 chip                      │
└─────────────────────────────────────────────────────┘
```

### 关键设计决策

1. **固定布局而非力导向图**。worker 数 ≤6（routing cap），五段泳道排得下；固定位置让用户每次看到的结构一致，"哪个阶段卡住了"一眼可见。不引入 React Flow 这类重依赖也能做（flex + SVG 边层），如果后续要拖动节点再上 XYFlow。
2. **边是叙事主角**。任务派发 = 信封图标沿 orc→worker 边滑动；worker 完成 = 边变实色；质检打回 = crt→worker 红色虚线边 + 卡片抖动一次 + "返工 R2" 徽章。PRD §8 的六类边模型直接用 `runGraph.ts` 里的 `EdgeType`。
3. **worker 卡片 = 迷你工位**，运行中显示：头像（assets/agents/<id>/headshot.png）+ 状态点 + `streamLog` 最后一条的 title（如"商品企划正在拆解货盘 / 价格带 / 波段"）+ 流式输出的尾部 2 行（`latestOutput` tail，打字机效果，`useTypewriter` 已有）。点击 → 打开现有 `NodeDetailFolder`。
4. **rework 可视化是灵魂**。这是"协同"区别于"并行打工"的瞬间：crt 卡片亮出 `fixes_required` 红徽章 → 红色回流边逐条点亮到被点名的 worker → 这些 worker 重新进入 running。哪怕用户没看懂细节，也能看懂"质检把活打回去了"。
5. **直答任务退化**：user → orc → final 三卡片简图（PRD 验收标准已有此要求）。
6. **舞台与桌面共存**：舞台是桌面上一个可最小化的大窗口（复用 FloatingWindow/WindowManager），run 开始自动弹出，结束后留存，点开任意历史会话可恢复（RunGraph 在 sessionStore 里）。

### 状态→视觉映射（直接对 `RunNodeStatus`）

| status | 视觉 |
|---|---|
| pending | 灰卡，头像降饱和 |
| running | 彩卡 + 呼吸光圈 + 流式尾巴 |
| completed | 绿勾角标 |
| needs_rework / reworking | 红角标 + 抖动一次 / 橙色"返工中" |
| validated | 蓝勾（critic 复核通过） |
| failed / timed_out | 红叉 / 沙漏，卡片置灰 |

### MVP 验收（对齐 PRD §16 的 6 件事）

跑一个完整企划任务，不点任何东西，用户能看出：谁被选中了、任务包飞给了谁、谁正在输出什么、质检过没过、打回了谁、最终产物从哪几个部门汇来。

## ② 产物看板（ArtifactBoard）

### 形态

`OutputsFolder`（现 163 行，纯文件列表）升级为看板窗口，**产物卡片**为单位：

```
┌─ 产物看板 ────────────────────────────────────┐
│ [筛选: 全部 | PPT | 详情页 | 小红书 | 报表]      │
│                                              │
│ ┌────────┐ ┌────────┐ ┌────────┐            │
│ │缩略图    │ │缩略图   │ │ ⏳生成中 │            │
│ │PPT 图标  │ │HTML图标 │ │         │           │
│ │秋冬企划会审│ │风衣详情页│ │库存周报  │            │
│ │✅已交付 v2│ │⚠️需返工 │ │质检中    │            │
│ │👤👤👤👤  │ │👤👤     │ │👤👤👤   │            │
│ └────────┘ └────────┘ └────────┘            │
└──────────────────────────────────────────────┘
```

每张卡片：

- **类型图标 + 标题**（deliverable_type + turn 标题）
- **状态徽章**＝质检门禁状态，不是文件状态：`生成中` / `质检中` / `⚠️ fixes_required`（黄）/ `✅ passed 已交付`（绿）/ `❌ 失败`。质检不过的产物在看板上就是黄的——把"质检门禁"做成用户可见的事实。
- **贡献者头像排**：来自 `department_results` 的 worker 头像，hover 显示"商品企划：SKU 结构"——产物和协同的连接点。
- **版本**：attempt_number ≥2 显示 `v2`，点开可比对返工前后。
- 操作：打开（系统默认应用）/ 在 Finder 显示 / 重新生成（带原 spec 重发）。

### 数据来源（零后端起步，两步到位）

1. **MVP**：`workflow_artifact`（含 deliverable_type_id、worker 结果、validation_report、文件路径）已经回传前端，sessionStore 按 run 聚合即可成卡。缩略图：PPT/xlsx 先用类型图标，HTML 详情页可 webview 截图。
2. **后续**：后端在 producer 层落地后（见 [handoff-producer-layer.md](handoff-producer-layer.md)），produce 节点把 `{file_path, deliverable_type_id, attempt, contributors, pass_gate}` 写成正式 artifact manifest（如 `data/outputs/manifest.jsonl`），看板改读 manifest，重启不丢。

## 实施顺序建议

1. CollabStage 静态布局 + RunGraph 渲染（1 个组件，吃现成 store）
2. 边动画 + 状态徽章 + rework 回流
3. ArtifactBoard MVP（聚合 workflow_artifact）
4. 缩略图 + manifest 持久化（等 producer 层）

## 不变量

- 用户不能连线、不能改历史 run（PRD §4.1）
- 不展示原始 chain-of-thought，只展示 run_step 摘要（PRD §4.3）
- UI 组件只消费 RunGraph，不直接碰原始事件（适配层已存在，别绕过）
