# Handoff: 产物模板库 + 产物制作能力强化

> 接手人请先读 [handoff-stategraph-and-kb.md](handoff-stategraph-and-kb.md) 了解 state graph + KB 现状；本文档只覆盖 2026-05-26 这一天新增的产物能力部分。

## 30 秒理解

boxcc 已经从「workers 产文字 → orc 用 create_pptx 把字塞进默认模板」升级为「workers 按模板 slot 出料 → orc 按 template recipe 组装 → 专业级导出工具渲染 → critic 按 quality_gates 评审」。

```
用户 "做季度复盘PPT" 
    → boxcc.md 注入 {deliverable_types} 列表
    → orc 匹配到 management_ppt 模板
    → 按 worker_contribution_map 写 chairman_plan，task packet 的 notes 告诉每个 worker 该填哪些 slot
    → 调 delegate_to_departments(..., deliverable_type_id="management_ppt")
    → workflow 把模板 quality_gates 渲染给 critic
    → critic 按 7 条 gates 评审
    → orc 调 create_management_ppt（6 种 slide 类型 + matplotlib 图表 + 品牌主题）
    → .pptx 落 backend/data/exports/{turn_id}/
```

## 今天加了什么

### 1. 产物导出工具（tools/）
- `tools/exports.py` — 通用：create_pptx / create_docx / create_xlsx / create_markdown（薄壳）
- `tools/management_ppt.py` + `ppt_theme.py` + `charts.py` — **管理层 PPT v2**：6 种 slide 类型（cover/agenda/divider/content/data/closing），3 套品牌主题（editorial/cool/warm），matplotlib 图表生成
- `tools/product_detail.py`（codex 写）— **商品详情页**：单文件 HTML，hero/highlights/fabric/size_table/scenes/care/faq/compliance_note

样品看：[~/Desktop/松林漫步-发布提案-v2.pptx](../../Desktop/松林漫步-发布提案-v2.pptx)、[~/Desktop/松林漫步-详情页.html](../../Desktop/松林漫步-详情页.html)

### 2. 产物模板库（deliverables/）
- Schema：`config/app_config.py` 加 `DeliverableTypeConfig` + `DeliverableSection`
- Registry：`deliverables/registry.py` — list / get / match（关键词路由）/ render_brief / describe
- 4 个已注册模板（在 `config.yaml` 末尾 `deliverable_types:` 段）：

| id | output | required workers | sections | gates |
|---|---|---|---|---|
| management_ppt | create_management_ppt | (open) | 6 类 slide | 7 |
| product_detail_page | create_product_detail_page | gro_content + biz_legal | 8 块 | 6 |
| xhs_note | create_markdown | gro_content + biz_legal | 9 段 | 7 |
| inventory_report | create_xlsx | biz_bi + mer_ops | 6 个 sheet | 6 |

### 3. Prompt + workflow 注入
- `agentspecs/boxcc.md` §5.5 加 `{deliverable_types}` 占位符（所有 agent 都看得到）
- `agentspecs/orc.md` 加章节 "Deliverable template flow"（教 orc 匹配 → 用 brief → 传 type_id → 调 output_tool）
- `subagents/tools.py` `delegate_to_departments` 加可选参数 `deliverable_type_id`
- `subagents/workflow.py` `_build_critic_task` 自动把 template 的 quality_gates 渲染到 critic prompt，要求 critic 在 `<validation_report>` summary 里逐条说明通过/失败

### 4. KB 真接（早些时候 codex 做的，本来就在范围内）
- chroma 接入完成，3/8 KB 已 ingest 真实文档：`compliance_contract_kb` / `brand_content_kb` / `fabric_test_kb`
- 种子文档在 `backend/data/kb_seed/{kb_id}/*.md`
- 已知问题：default embedding 是 all-MiniLM-L6-v2（英文模型），中文 score 趋 0 但排序仍可用。生产前切 `BAAI/bge-small-zh-v1.5`，config 里改 `embedding_model` 然后重跑 ingest

## 关键文件

```
backend/
├── config.yaml                          ← deliverable_types 末尾
├── agentspecs/
│   ├── boxcc.md                         ← §5.5 占位符
│   └── orc.md                           ← "Deliverable template flow" 章节
├── config/app_config.py                 ← DeliverableTypeConfig schema
├── deliverables/
│   ├── __init__.py
│   └── registry.py                      ← 核心：match / get / render_brief
├── tools/
│   ├── __init__.py
│   ├── exports.py                       ← 薄壳 (pptx/docx/xlsx/md)
│   ├── management_ppt.py                ← PPT v2 builder
│   ├── ppt_theme.py                     ← 3 主题 + 设计 tokens
│   ├── charts.py                        ← matplotlib 主题化
│   └── product_detail.py                ← HTML PDP
├── subagents/
│   ├── tools.py                         ← delegate_to_departments 加参数
│   └── workflow.py                      ← critic 注入 quality_gates
└── agents/master_prompt.py              ← {deliverable_types} 渲染
```

## 还没做（按优先级）

**A. 真实 e2e 验证模板驱动流程（关键，没花预算跑）**
- 测试 prompt：「帮我做 Q3 库存复盘 PPT，重点看滞销和补货建议」
- 预期：orc 自动匹配 management_ppt（不是 inventory_report，因为用户明确说 PPT）；critic 按 7 条 gates 审；最终落 .pptx
- 怎么跑：参考 `backend/scripts/heavy_test.py`（已实现完整 hook 抓包 + state dump），改 PPT_TASK 即可

**B. Producer agent 层**（用户原始要求里的第二轴）
- 现在 orc 既负责选模板又负责填 spec，prompt 压力大
- 加一个 `producer` 专员角色：worker 完成后，producer 把多份 worker 文本翻成 spec_json，再调 export 工具
- 可选：每种产物类型一个 producer，或一个通用 producer 读模板 brief 工作
- 改动面：subagents/registry 加 producer、workflow 在 critic 通过后调 producer 而非让 orc 直接调 export tool

**C. 加更多产物形态**（用户原始第三轴）
- 报告 §7.1 还有 6 种：商品标题/EDM/直播话术/FAQ/趋势报告/KOL brief/VM 陈列指引
- 用 codex，每个模板 30 分钟搞定（参考 xhs_note / inventory_report 的写法）

**D. 5 个 noop KB 真接**
- product_catalog_kb / supplier_capacity_kb / sales_inventory_kb / platform_rules_kb / voc_kb
- 写种子文档 → ingest → 改 retriever: chroma

**E. 字符级别小优化**
- critic 任务 16K 截断已有，但 worker output > 3500 字会被砍头尾。生产可考虑加摘要式压缩
- orc.md 里 "一次 delegate per turn" 规则已有，但 PPT 测试中观察到 orc 偶尔会犹豫；可加更强的 "if critic returned and critic.pass_gate==fixes_required AND deliverable_type was declared, GO TO output_tool immediately"

## 关键 gotcha

1. **ikuncode 代理 16K user message 限制**：critic round-1 容易撞上，已用 `_truncate_worker_summary` + `_compact_packets` + 14K hard cap 三层防御
2. **PPT 渲染**：默认用 blank layout 手工定位，**不依赖 .pptx 模板文件**（避免环境差异）
3. **chroma onnx 模型 ~80MB 在 ~/.cache/chroma**：codex 沙箱不能写 home，让 codex 跑 ingest 会卡权限；用主 shell 跑
4. **`worker_contribution_map` 是软约束**：orc prompt 里描述了，但没有 schema 强制校验。worker 不一定严格按 section 出料；如果发现问题，可在 `validate_chairman_plan` 里加校验
5. **gpt-5.5 via ikuncode API**：[.env](../backend/.env) 里有 key（已被 `.gitignore`）。账户余额查 https://api.ikuncode.cc

## 当前状态

- `git status` 应该看得到一堆未提交改动（config.yaml / agentspecs/*.md / 多个新文件）
- 我没主动 git commit；接手人按需提交
- 所有静态检查通过：import 链通畅、graph 编译通过、registry 加载通过、4 个模板都 register
- 原 handoff 时没跑真实 LLM e2e 验证；后续 Codex 已补跑，见下一段

### 2026-05-26 Codex follow-up：e2e 已跑

已按下面的「接手第一件事建议」跑过真实 e2e，并修掉几处链路问题：

- `agents/lead_agent.py` 原先只注册了旧导出工具（`create_pptx/docx/xlsx/md`），导致 orc 即使匹配 `management_ppt` 也看不到 `create_management_ppt`。已把 `create_management_ppt` 和 `create_product_detail_page` 加入 lead agent 工具列表。
- `agentspecs/orc.md` 的 File export tools 表仍把 PPT 指向旧 `create_pptx`。已补充 `create_management_ppt` / `create_product_detail_page`，并把 `create_pptx` 降为轻量普通幻灯片 fallback。
- `tools/management_ppt.py` 的 `closing.actions` 只接受 dict，模型给字符串时会崩；`data.chart.series` 只接受 dict，模型常给 `[{name, values}]`。已加宽容解析，支持这两种常见 LLM spec 形态。
- `scripts/heavy_test.py` 的 session store 隔离不彻底：`WorldStateMiddleware` / `session.checklist` 在 override 前已经绑定旧 `get_session_store`，导致 e2e 可能混入旧 world_state。已 patch 这些模块引用，确保每次 heavy test 用临时 data dir 的干净 session。

最终干净 e2e 结果：

- 命令：`"/Users/niuniu/Desktop/boxcc 1.0/.venv/bin/python" scripts/heavy_test.py`
- data dir：`/var/folders/gm/pzvqcjkx47q6vr_kgyds3fp80000gn/T/boxcc-heavy-13lnfu0d`
- raw capture：`/var/folders/gm/pzvqcjkx47q6vr_kgyds3fp80000gn/T/boxcc-heavy-13lnfu0d/raw_capture.json`
- report：`/var/folders/gm/pzvqcjkx47q6vr_kgyds3fp80000gn/T/boxcc-heavy-13lnfu0d/heavy_test_report.json`
- 产物：`/var/folders/gm/pzvqcjkx47q6vr_kgyds3fp80000gn/T/boxcc-heavy-13lnfu0d/exports/msg-heavy-1/Q3商品复盘-滞销补货价格策略-数据待填版.pptx`（106,311 bytes）
- raw capture 关键确认：
  - `delegate_to_departments` 参数包含 `"deliverable_type_id": "management_ppt"`
  - critic prompt / validation 中出现 management_ppt 的 template gates
  - final export 调用 `create_management_ppt`，没有 fallback 到 `create_pptx`

残留风险：

- ikuncode 在一次 `mer_ops` rework 调用中返回过 `403 bad_response_status_code`，workflow 仍用已有 worker 输出继续生成了「数据待填版」PPT。这个更像上游模型服务/代理波动，不是本地工具崩溃。
- critic 的 recheck 发生在最终 export 之前，所以它仍会说「未见真实 .pptx 文件」。orc 随后生成了文件并在最终回复给路径。若要质量闭环更严谨，需要把 artifact 生成移到 critic 可见的 producer/export 阶段，或在最终 export 后追加轻量 artifact verification。
- session state 里 `last_run_status` / `orc_final` 在 heavy test report 中仍显示 running，虽然最终回答和文件已生成。需要后续把 lead-agent final export 后的状态落库补齐。
- 本轮 `sales_inventory_kb` 仍是 noop，因此库存复盘只能生成「数据待填版」，无法满足“至少 1 张真实数字驱动 data slide”的质量门。

## 接手第一件事建议

跑一次端到端：

```bash
cd "/Users/niuniu/Desktop/boxcc 1.0/backend"
# 改 scripts/heavy_test.py 的 PPT_TASK 为 "做一份 Q3 商品复盘 PPT，看滞销 + 补货 + 价格策略"
"/Users/niuniu/Desktop/boxcc 1.0/.venv/bin/python" scripts/heavy_test.py
```

看 raw_capture.json 里 `delegate_to_departments` 工具调用有没有 `deliverable_type_id` 字段，critic prompt 有没有 `Deliverable quality gates` 段，final answer 有没有调 `create_management_ppt`。

如果 orc 没自动用模板 → 看 orc.md prompt 的清晰度，可能要 tone up。
如果 orc 用了但产物质量还是不够 → 看 template `notes` 是否描述够具体。
