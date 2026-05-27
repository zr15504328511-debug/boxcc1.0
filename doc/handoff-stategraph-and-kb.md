# Handoff: StateGraph 编排 + 真实 KB 接入

> 写给下一位（包括未来的我）接手者。覆盖两件事：
> 1. boxcc 的 delegate workflow（LangGraph StateGraph）现在长什么样、怎么扩展
> 2. 怎么把 `query_knowledge_base` 工具的 Noop retriever 换成真实检索后端
>
> 阅读对象假设：会基本 Python + 看过 [PROJECT_SPEC.md](../PROJECT_SPEC.md) 的概览。
> 最后更新：2026-05-25

---

## 第 0 节 - 30 秒读懂当前架构

```
用户 → Electron 前端 → FastAPI /api/chat → Lead Agent (orc)
                                              ↓ 调 tool
                                  delegate_to_departments
                                              ↓ 验证 + 路由后
                                  run_delegate_workflow (StateGraph)
                                              ↓ Send 并行
                                  N 个 worker agent (含 KB tool)
                                              ↓
                                  critic (crt) 评审 → 可选 rework loop
                                              ↓
                                  finalize → 返回 (content, artifact) 给 orc
                                              ↓
                                  orc 综合后给用户最终答复
```

**关键文件**：
- [`backend/subagents/workflow.py`](../backend/subagents/workflow.py) — **整个 delegate workflow 的 StateGraph 定义**
- [`backend/subagents/tools.py`](../backend/subagents/tools.py) — 薄壳 tool，做 JSON 验证 + 路由检查后调 workflow
- [`backend/subagents/executor.py`](../backend/subagents/executor.py) — `_run_department` 单个 worker 执行（被 workflow 的 node 调用）
- [`backend/knowledge/tools.py`](../backend/knowledge/tools.py) — `query_knowledge_base` 工具 + contextvar 白名单
- [`backend/knowledge/registry.py`](../backend/knowledge/registry.py) — KB 注册查询 + retriever 缓存
- [`backend/knowledge/retriever.py`](../backend/knowledge/retriever.py) — `BaseRetriever` 协议 + `NoopRetriever` 默认实现
- [`backend/config.yaml`](../backend/config.yaml) `knowledge_bases:` — KB 注册表

---

## 第 1 节 - StateGraph：现状

### 1.1 节点拓扑（11 个节点）

```
START
  ↓
[dispatch_workers]                    # 发出 "Phase 1 开始" 事件，无副作用
  │
  ↓ Send fan-out (动态)
[run_worker × N]                      # 每个被选 worker 跑一个实例，并行
  │
  ↓ reducer 合并结果（operator.add）
[aggregate_workers]                   # 把 N 个 worker 输出拼成 summary
  │
  ↓
[run_critic]                          # 跑 crt agent，得到 validation_report
  │
  ↓ conditional edge (decide_rework)
  ├── pass / passed / failed → [finalize] → END
  └── fixes_required → [dispatch_rework]
                            │
                            ↓ Send fan-out
                       [run_rework_worker × M]
                            │
                            ↓
                       [aggregate_rework]
                            │
                            ↓
                       [run_critic_recheck]   # 第二次 crt 复核
                            │
                            ↓
                       [finalize] → END
```

### 1.2 State schema

定义在 [`workflow.py`](../backend/subagents/workflow.py) 顶部的 `WorkflowState` TypedDict。

**重点关注三个使用 `Annotated[list, operator.add]` 的字段**：

| 字段 | 用途 | 为什么用 reducer |
|---|---|---|
| `worker_results` | 收集每个 worker 的 `DepartmentResult` 对象 | Send 并行触发多个 `run_worker`，每个返回一个结果，reducer 把它们 append 到同一 list |
| `worker_output_parts` | 收集每个 worker 的输出 markdown 段 | 同上 |
| `department_results` | 收集 worker + critic 的 serialized dict（用于 artifact） | 同上 |

**没有 reducer 的字段**走"最后写入覆盖"语义。例如 `critic_result`、`validation_report` 都是单值——critic 节点会直接覆盖。

### 1.3 节点函数的接口约定

- **普通节点** `async def node(state: WorkflowState) -> dict`：返回的 dict 会合并进 state（按字段名）
- **Send 节点** `async def run_worker(node_input: dict) -> dict`：node_input 是 Send 时传入的 ad-hoc 字典，返回的 dict 走 reducer 合并到 parent state
- **条件边函数** `def decide_rework(state) -> str`：同步函数，返回下一个节点名（字符串，必须在 `add_conditional_edges` 的 mapping 里）
- **Send fan-out 函数** `def _fanout_workers(state) -> list[Send]`：同步函数，返回 Send 对象列表

### 1.4 事件流 / 会话状态副作用

所有 `emit_run_step` 和 `OrcSessionState` 的更新（`update_checklist_item` / `upsert_worker_shard` / `set_validation_report` 等）**直接在节点函数里调用**。LangGraph 不管这些副作用，纯粹靠 contextvar（`runtime_events._event_session_id_var`）传递 session_id。

**这意味着**：如果你将来想做时间回溯（time-travel debug），单纯重放 StateGraph 不够——还要重放副作用。这是个已知缺点。

---

## 第 2 节 - StateGraph：怎么扩展（常见动作）

### 2.1 加一个新节点（不改流程拓扑）

最常见场景：想在 critic 之前插入一个"预审"节点。

```python
# workflow.py
async def pre_check(state: WorkflowState) -> dict:
    """Quick sanity check before invoking critic."""
    if not state.get("worker_results"):
        return {"validation_report": ValidationReport(pass_gate="failed", summary="no worker output")}
    return {}  # pass through

def build_delegate_graph():
    g = StateGraph(WorkflowState)
    # ... 现有节点 ...
    g.add_node("pre_check", pre_check)
    # 改一条边
    g.add_edge("aggregate_workers", "pre_check")
    g.add_edge("pre_check", "run_critic")
    # 其他边不动
```

### 2.2 接 LangGraph 的 SqliteSaver checkpointer（让 workflow 可断点续跑）

**目前没接**，主要因为 chat.py 调用 `delegate_to_departments` 的 thread_id 跟 lead agent 的 thread_id 是同一个，分层管理需要想清楚。

接的步骤：

```python
# workflow.py
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

async def get_delegate_graph_with_checkpointer(db_path: str):
    g = build_delegate_graph_unfinalized()  # 改 build_delegate_graph 返回未 compile 的 StateGraph
    saver = AsyncSqliteSaver.from_conn_string(db_path)
    return g.compile(checkpointer=saver)
```

然后在 `run_delegate_workflow` 调用时传 `config={"configurable": {"thread_id": f"delegate-{session_id}-{turn_id}"}}`。

**注意点**：副作用（emit_run_step、OrcSessionState 写入）在断点续跑时**会重复触发**。需要给节点加幂等性（用 step_id 去重 emit、检查 OrcSessionState 当前状态决定是否再写）。

### 2.3 加一种新的"评审策略"（不止 critic 一个评审者）

例如想让 `biz_legal` 在所有涉及合同的 worker 完成后做一次"合规 quick check"，然后才进 crt。

```python
def decide_post_worker(state):
    # 看 routing_policy 是不是有合同/合规标签
    if state["routing_policy"]["rationale"].find("合同") >= 0:
        return "run_legal_check"
    return "run_critic"

# build_delegate_graph 里：
g.add_node("run_legal_check", run_legal_check)
g.add_conditional_edges("aggregate_workers", decide_post_worker, {
    "run_legal_check": "run_legal_check",
    "run_critic": "run_critic",
})
g.add_edge("run_legal_check", "run_critic")
```

### 2.4 改并行/串行行为

**当前所有 worker 是真并行**（Send + reducer）。要改成串行（例如总是按 `dom → ana → cpy` 顺序），把 `_fanout_workers` 改成不用 Send，而是改成顺序节点链：

```python
def next_worker(state):
    done = {r.id for r in state["worker_results"]}
    pending = [aid for aid in state["selected_ids"] if aid not in done]
    return "run_one_worker" if pending else "aggregate_workers"

# 单 worker 节点改成"取第一个未完成的跑"
async def run_one_worker(state):
    done = {r.id for r in state.get("worker_results", [])}
    aid = next(aid for aid in state["selected_ids"] if aid not in done)
    result = await _run_department(state["worker_map"][aid], state["tasks"][aid])
    return {"worker_results": [result], "worker_output_parts": [_build_output_section(result)]}
```

**反过来**，如果想给 `run_critic_recheck` 也加并行（多个 critic 同时审），方法同 `dispatch_workers`：发 Send，配 reducer。

### 2.5 调试技巧

LangGraph 编译后的 graph 可以 dump 成 mermaid：

```python
from subagents.workflow import get_delegate_graph
print(get_delegate_graph().get_graph().draw_mermaid())
```

跑一次（mock LLM）观察 state 流转：

```python
final = await graph.ainvoke(initial_state, stream_mode="values")
# 或用 astream 看每一步
async for chunk in graph.astream(initial_state, stream_mode="updates"):
    print(chunk)
```

---

## 第 3 节 - 真实 KB 接入：现状

### 3.1 三层 KB 控制

| 层 | 在哪里 | 控制什么 |
|---|---|---|
| **L1：系统注册** | [`config.yaml`](../backend/config.yaml) `knowledge_bases:` | 平台层面"有哪些 KB 可用" |
| **L2：agent 声明范围** | `config.yaml` 每个 agent 的 `kb_refs` 字段 | 这个 agent **可能**用到的 KB（如商品企划可声明 `[product_catalog_kb, sales_inventory_kb]`） |
| **L3：本次任务授权** | orc 在 `chairman_plan` 里给每个 task_packet 填的 `kb_refs` | orc 决定**本轮**真正放行哪些 |

**实际生效的白名单** = L2 ∩ L3（[`executor.py:_run_department`](../backend/subagents/executor.py) 计算）。若 orc 没填，回退到 L2 全集。

### 3.2 执行链路

```
executor 调 _run_department(dept, packet)
  ↓ 计算 effective_kb_refs = dept.kb_refs ∩ packet.kb_refs
  ↓ set_kb_allowlist(effective_kb_refs) → 写 contextvar
  ↓
worker agent.ainvoke()
  ↓ worker LLM 决定调 query_knowledge_base(kb_id=..., query=...)
  ↓
knowledge/tools.py query_knowledge_base
  ↓ 检查 get_kb_allowlist() —— 不在白名单立刻返回错误信息
  ↓ get_retriever(kb_id) → 拿到 BaseRetriever 实例
  ↓ retriever.retrieve(query, k=5)
  ↓ 格式化成文本返回给 LLM
  ↓
finally: reset_kb_allowlist(token)
```

### 3.3 当前 retriever 实现

只有 [`NoopRetriever`](../backend/knowledge/retriever.py)，返回一句"未配置实际检索器"的占位文本。所有 8 个 KB（`product_catalog_kb` / `fabric_test_kb` / `supplier_capacity_kb` / `sales_inventory_kb` / `platform_rules_kb` / `brand_content_kb` / `compliance_contract_kb` / `voc_kb`）都用 Noop。

---

## 第 4 节 - 真实 KB 接入：怎么换实现

### 4.1 BaseRetriever 协议

定义在 [`knowledge/retriever.py`](../backend/knowledge/retriever.py)：

```python
class BaseRetriever(Protocol):
    def retrieve(self, query: str, *, k: int = 5) -> list[RetrievalChunk]: ...

@dataclass
class RetrievalChunk:
    source: str        # 来源标识（"kb://fabric_test_kb" / 文档名 / URL）
    content: str       # 命中的文本片段
    score: float = 0.0 # 相关性分数（0-1，越高越相关）
```

**implementer 只需实现一个同步 `retrieve` 方法**。如果你的检索是 IO bound，可以在内部用 `asyncio.run_coroutine_threadsafe` 跑异步代码，或者直接用同步 HTTP/SDK 客户端。

### 4.2 路径 A：本地向量库（ChromaDB）

适合：单机部署、想快速试一遍 RAG 闭环、文档量不大（< 10 万 chunk）。

**新建文件** `backend/knowledge/chroma_retriever.py`：

```python
from chromadb import PersistentClient
from chromadb.utils import embedding_functions
from knowledge.retriever import BaseRetriever, RetrievalChunk

class ChromaRetriever:
    def __init__(self, kb_id: str, description: str = "", config: dict | None = None):
        cfg = config or {}
        self.kb_id = kb_id
        self.client = PersistentClient(path=cfg.get("path", f"data/kb/{kb_id}"))
        # 用本地 sentence-transformer 模型（无需 API key）
        embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=cfg.get("embedding_model", "BAAI/bge-small-zh-v1.5"),
        )
        self.collection = self.client.get_or_create_collection(
            name=kb_id, embedding_function=embed_fn,
        )

    def retrieve(self, query: str, *, k: int = 5) -> list[RetrievalChunk]:
        results = self.collection.query(query_texts=[query], n_results=k)
        out = []
        for i, (doc, meta, dist) in enumerate(zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        )):
            score = max(0.0, 1.0 - dist)  # chroma 距离 → 相似度
            out.append(RetrievalChunk(
                source=meta.get("source", f"chroma://{self.kb_id}/{i}"),
                content=doc,
                score=score,
            ))
        return out
```

**注册到 retriever 工厂**：[`knowledge/retriever.py`](../backend/knowledge/retriever.py) 末尾的 `_RETRIEVER_TYPES`：

```python
_RETRIEVER_TYPES: dict[str, type] = {
    "noop": NoopRetriever,
    "chroma": ChromaRetriever,   # 新增
}
```

`build_retriever` 已经支持任意类型；不在 dict 里的会 fallback 到 Noop。

**改 config.yaml**：

```yaml
knowledge_bases:
  - id: fabric_test_kb
    name: 面辅料与测试知识库
    description: ...
    retriever: chroma           # 从 noop 换成 chroma
    config:
      path: data/kb/fabric_test_kb
      embedding_model: BAAI/bge-small-zh-v1.5
```

**还需要做 ingest**（把企业文档喂进去）：写一个 `scripts/ingest_kb.py`，遍历文档 → 切分 → `collection.add(documents=[...], metadatas=[...], ids=[...])`。这是一次性 / 增量任务，跟 boxcc 主进程解耦。

### 4.3 路径 B：HTTP RAG 服务（企业现有 RAG 平台）

适合：公司已有 RAG 平台（Dify / Coze / 自建），boxcc 只做调用。

**新建** `backend/knowledge/http_retriever.py`：

```python
import httpx
from knowledge.retriever import BaseRetriever, RetrievalChunk

class HttpRetriever:
    """Calls an external RAG endpoint that returns {chunks: [{source, content, score}, ...]}."""

    def __init__(self, kb_id: str, description: str = "", config: dict | None = None):
        cfg = config or {}
        self.kb_id = kb_id
        self.endpoint = cfg["endpoint"]              # required
        self.api_key = cfg.get("api_key", "")
        self.timeout = cfg.get("timeout_seconds", 15)
        self.collection_name = cfg.get("collection", kb_id)

    def retrieve(self, query: str, *, k: int = 5) -> list[RetrievalChunk]:
        payload = {"query": query, "k": k, "collection": self.collection_name}
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        try:
            r = httpx.post(self.endpoint, json=payload, headers=headers, timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
        except Exception as exc:
            return [RetrievalChunk(source=f"http://{self.kb_id}", content=f"(retrieve error: {exc})")]
        return [
            RetrievalChunk(
                source=item.get("source", f"http://{self.kb_id}"),
                content=item.get("content", ""),
                score=float(item.get("score", 0.0)),
            )
            for item in data.get("chunks", [])[:k]
        ]
```

注册同上。config.yaml：

```yaml
knowledge_bases:
  - id: voc_kb
    name: VOC 与客诉知识库
    retriever: http
    config:
      endpoint: https://rag.your-company.com/v1/retrieve
      api_key: $RAG_API_KEY           # 从 .env 读
      collection: voc_2026
```

**`$RAG_API_KEY` 走 .env**：[`config/app_config.py`](../backend/config/app_config.py) 的 `resolve_env_variables` 已经处理了 `$XXX` 语法。

### 4.4 路径 C：直接接 LangChain 的 VectorStore

适合：想复用 LangChain 生态的现成 retriever（FAISS / Pinecone / Weaviate / Milvus）。

```python
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
from knowledge.retriever import RetrievalChunk

class LangChainRetriever:
    def __init__(self, kb_id: str, description: str = "", config: dict | None = None):
        cfg = config or {}
        embeddings = HuggingFaceEmbeddings(model_name=cfg.get("embedding_model", "BAAI/bge-small-zh-v1.5"))
        self.store = FAISS.load_local(cfg["path"], embeddings, allow_dangerous_deserialization=True)
        self.kb_id = kb_id

    def retrieve(self, query: str, *, k: int = 5) -> list[RetrievalChunk]:
        docs_and_scores = self.store.similarity_search_with_score(query, k=k)
        return [
            RetrievalChunk(
                source=doc.metadata.get("source", f"faiss://{self.kb_id}"),
                content=doc.page_content,
                score=float(1.0 / (1.0 + score)),  # FAISS 距离 → 相似度
            )
            for doc, score in docs_and_scores
        ]
```

### 4.5 给 worker 看的检索结果格式

[`knowledge/tools.py::_format_chunks`](../backend/knowledge/tools.py) 决定 LLM 看到啥。当前格式：

```
[KB:fabric_test_kb] retrieved 3 chunk(s):
  (1) source=doc://面料标准.pdf#section-3 score=0.87
      莱赛尔混纺一般缩水率 1.5%-3%，需经预缩处理...
  (2) source=... score=...
      ...
```

如果你的 retriever 返回结构化字段（如表格），可以在 retriever 实现里直接把表格 markdown 化塞进 `content`，或者改 `_format_chunks` 让它识别 metadata。

### 4.6 测试一个新 retriever

```python
from knowledge.registry import reset_registry_cache, get_retriever
from config.app_config import reload_app_config

reload_app_config()  # 重读 config.yaml
reset_registry_cache()  # 清掉之前的 retriever 缓存

r = get_retriever("fabric_test_kb")
chunks = r.retrieve("莱赛尔缩水率", k=3)
for c in chunks:
    print(c.score, c.source, c.content[:100])
```

**端到端测**（受 contextvar 白名单约束的真实工具调用）：

```python
from knowledge.tools import query_knowledge_base, set_kb_allowlist, reset_kb_allowlist

tok = set_kb_allowlist(["fabric_test_kb"])
try:
    print(query_knowledge_base.invoke({"kb_id": "fabric_test_kb", "query": "缩水率"}))
finally:
    reset_kb_allowlist(tok)
```

### 4.7 Known limitations

ChromaDB 的默认 embedding function 是 `all-MiniLM-L6-v2`，英文语义检索表现更稳定；用于中文服装业务文档时，排序通常仍可用，但 Chroma 返回的距离可能接近 1，按 `score = max(0.0, 1.0 - distance)` 归一化后相关性分数会偏低甚至显示为 `0.00`。这不一定代表没有命中，而是默认 embedding 与中文语料的相似度标尺不准。

生产环境建议切换中文 embedding，例如 `BAAI/bge-small-zh-v1.5`。当前 `ChromaRetriever` 已预留 `config["embedding_model"]`，可在 `config.yaml` 的对应 KB 下配置后重建/重跑 ingest；注意查询端和 ingest 端必须使用同一 embedding 模型，避免新旧向量空间混用。

---

## 第 5 节 - 产物模板库

产物模板统一配置在 [`backend/config.yaml`](../backend/config.yaml) 的 `deliverable_types:` 段。每个模板描述一种最终成品的骨架、触发词、推荐参与 worker、输出工具和 critic 评审口径；orc 根据用户请求匹配模板，再把结构要求分配给对应 worker。

字段要点：

- `id` / `name` / `description`：模板唯一标识、展示名称和适用场景。
- `triggers`：用户请求里出现这些关键词时优先匹配该模板。
- `output_tool` / `default_theme`：最终调用哪个导出工具，以及默认主题参数（如果该工具支持）。
- `voice`：成品文风和表达边界，给 orc 和 worker 统一语气。
- `suggested_workers` / `required_workers`：建议参与和必须参与的 worker；required worker 缺失时应返工。
- `structure`：成品 section / sheet / page 的顺序骨架；每项至少包含 `type`、`required`、`min_count`、`max_count`，复杂 slot 用中文 `notes` 说明怎么填。
- `worker_contribution_map`：把 worker 输出映射到具体 section，驱动 chairman_plan。
- `quality_gates`：critic 审稿 checklist，必须写成可执行的验收条件。

新增模板步骤：

1. 在 `deliverable_types:` 末尾追加一条，不改已有模板 id 和字段。
2. 先确定 `output_tool`。例如 `xhs_note` 暂用 `create_markdown`，因为它产出单篇小红书文案；`inventory_report` 用 `create_xlsx`，因为它天然是多 sheet 库存表。
3. 写 `triggers`，覆盖用户真实说法和英文/缩写说法。例如 `xhs_note` 同时包含“小红书”“xhs”“笔记”“种草”“社媒文案”“小红书选题”。
4. 写 `structure`，把成品拆成 orc 能填的 slot。`xhs_note` 拆成 `title`、`hook`、`pain_points`、`product_intro`、`try_on`、`outfit_combos`、`tips`、`hashtags`、`compliance_note`。
5. 写 `worker_contribution_map` 和 `quality_gates`，确保 required worker 的输入能支撑所有必备 section。

本地 smoke：

```bash
cd /Users/niuniu/Desktop/boxcc\ 1.0/backend
/Users/niuniu/Desktop/boxcc\ 1.0/.venv/bin/python -c "
from config.app_config import reload_app_config
reload_app_config()
from deliverables import list_deliverable_types, match_deliverable_type, render_deliverable_brief
ids = [getattr(t, 'id', '') for t in list_deliverable_types()]
print('registered:', ids)
assert 'xhs_note' in ids and 'inventory_report' in ids
for q in ['写一篇小红书笔记', '做一份本周库存分析', '滞销分析']:
    print(f'  {q!r} -> {match_deliverable_type(q)}')
print('--- xhs_note brief (head 25) ---')
print('\n'.join(render_deliverable_brief('xhs_note').splitlines()[:25]))
print('--- inventory_report brief (head 25) ---')
print('\n'.join(render_deliverable_brief('inventory_report').splitlines()[:25]))
"
```

---

## 第 6 节 - 已知问题 / 待办

| 问题 | 严重度 | 备注 |
|---|---|---|
| StateGraph 副作用不可重放 | 中 | 节点直接调用 emit / OrcSessionState 写入，断点续跑会重复触发。接 checkpointer 时需要给节点加幂等性 |
| Retriever 是同步接口 | 低 | LangChain tool 调用是同步语境；如果你的 HTTP retriever 慢（>2s）会卡 worker。可改用 `httpx.AsyncClient` + `asyncio.run_until_complete` 包装 |
| 真实 retriever 的失败处理 | 中 | 当前 retriever 异常会被 [`tools.py::query_knowledge_base`](../backend/knowledge/tools.py) 捕获返回错误字符串。worker LLM 可能不识别错误重试，应在 prompt 里教它"看到 retrieve error 不要重试" |
| KB 注入没走 prompt cache 友好顺序 | 低 | KB 描述列表注入在 [`boxcc.md`](../backend/agentspecs/boxcc.md) 的 `{knowledge_bases_description}` 占位，加新 KB 会改变 master prompt 前缀 → 第二轮 cache miss 一次。可接受 |
| 没有 KB 用量统计 | 低 | 没有记录"哪个 worker 在哪轮调了哪个 KB 多少次"。要加的话在 [`tools.py::query_knowledge_base`](../backend/knowledge/tools.py) 里加日志 / OrcSessionState 字段 |

---

## 第 7 节 - 接手 checklist

如果你刚拿到这份文档，按这个顺序熟悉：

1. 跑 [`backend/sitecustomize.py`](../backend/sitecustomize.py) 旁边的 smoke：`python -c "from agents.lead_agent import make_lead_agent; make_lead_agent('deepseek-v3')"`，验证 import 链通
2. 看 [`workflow.py`](../backend/subagents/workflow.py) 末尾 30 行的 `build_delegate_graph()` —— 拓扑一目了然
3. 看 [`knowledge/tools.py`](../backend/knowledge/tools.py) —— 100 行内，看完就懂三层授权
4. 改一个小东西验证你能动手：
   - 试 §2.1 加一个 pre_check 节点
   - 试 §4.2 起一个本地 chroma + ingest 10 篇文档 + 跑一次真实检索
5. 看 [`agentspecs/boxcc.md`](../backend/agentspecs/boxcc.md) 第 4 节 KB 使用规则——这是 LLM 看到的最高优先级规则，改它影响所有 agent

---

## 第 8 节 - 2026-05-27 清理后恢复说明

本节记录一次项目目录瘦身后的状态，避免接手人把可再生目录的缺失误判为源资料丢失。

### 8.1 需要重建的可再生内容

| 项 | 影响 | 恢复方式 |
|---|---|---|
| `.venv/` | Python 虚拟环境已清理 | 在项目根目录跑 `python3.12 -m venv .venv`，再安装 backend |
| `node_modules/` | Electron / Node 依赖已清理 | 在项目根目录跑 `npm install` |
| `backend/data/kb/` | 3 个 Chroma 向量库已清理：`compliance_contract_kb` / `brand_content_kb` / `fabric_test_kb` | 用 `backend/data/kb_seed/` 里的种子文档重新 ingest |
| `backend/data/checkpoints.db` | 旧测试 checkpoint 不在当前目录 | 不需要手动恢复，运行时会自动创建 |

### 8.2 已确认保留

- [`backend/.env`](../backend/.env) 仍在，`IKUNCODE_API_KEY` 保留
- [`backend/data/kb_seed/`](../backend/data/kb_seed/) 仍在，3 个 KB 共 9 篇种子文档保留
- [`backend/data/orc_sessions.json`](../backend/data/orc_sessions.json) 仍在，历史会话状态保留
- 今天新增的源代码与配置仍在，包括 `tools/`、`deliverables/`、`agentspecs/boxcc.md`、template、registry、[`backend/pyproject.toml`](../backend/pyproject.toml)、[`package.json`](../package.json)、[`backend/config.yaml`](../backend/config.yaml)

### 8.3 已确认安全删除

- `_live` 系列文件：`executor_live.py` / `tools_live.py` / `chat_live.py` / `prompt_live.py`。这是 18-agent 重构后的废弃版本，说明见 [`sitecustomize.py`](../backend/sitecustomize.py) 注释。
- 老 4-agent 时代的 `ana.md` / `cpy.md` / `dom.md` / `pln.md`。已由 18 个 specialist agent spec 替代。
- `PROJECT_SPEC.md` / `agent-memory-execution-plan.md`。属于旧规划文档，已由 handoff 文档承接；旧 handoff 里如仍有 Markdown 链接指向 `PROJECT_SPEC.md`，不影响当前启动。

### 8.4 接手人启动序列

```bash
cd "/Users/niuniu/Desktop/boxcc 1.0"
python3.12 -m venv .venv
.venv/bin/pip install -e backend
.venv/bin/pip install python-pptx python-docx openpyxl chromadb matplotlib

cd backend
../.venv/bin/python scripts/ingest_kb.py --kb-id compliance_contract_kb --source-dir data/kb_seed/compliance_contract_kb
../.venv/bin/python scripts/ingest_kb.py --kb-id brand_content_kb --source-dir data/kb_seed/brand_content_kb
../.venv/bin/python scripts/ingest_kb.py --kb-id fabric_test_kb --source-dir data/kb_seed/fabric_test_kb

../.venv/bin/python scripts/heavy_test.py
```

第一次 Chroma ingest 可能会下载约 79MB ONNX 模型到 `~/.cache/chroma`；缓存完成后后续会快很多。

---

## 附录 A - 关键 import 速查

```python
# StateGraph 编排
from subagents.workflow import (
    build_delegate_graph,    # 重新编译图（开发时调试用）
    get_delegate_graph,      # 拿全局编译过的图（生产用）
    run_delegate_workflow,   # 高层 API，tools.py 调这个
    WorkflowState,           # state schema
)

# KB
from knowledge.registry import (
    describe_knowledge_bases,  # 给 boxcc.md 用的 markdown 列表
    get_knowledge_base,        # 拿单个 KB 的 config 对象
    get_retriever,             # 拿 retriever 实例（带 lru_cache）
    reset_registry_cache,      # 清缓存（config 重新加载后调）
)
from knowledge.retriever import (
    BaseRetriever, RetrievalChunk, NoopRetriever,
    build_retriever,           # retriever 工厂
    _RETRIEVER_TYPES,          # 注册新类型加这里
)
from knowledge.tools import (
    query_knowledge_base,      # @tool —— LLM 调的
    set_kb_allowlist,          # contextvar set（executor 调）
    reset_kb_allowlist,        # contextvar reset（finally 调）
    get_kb_allowlist,          # 读当前白名单（tool 自己用）
)
```

## 附录 B - 字段对齐速查

| 概念 | config.yaml | AppConfig | SubagentConfig | task_packet |
|---|---|---|---|---|
| Agent id | `agents.registry[].id` | `agent.id` | `dept.id` | (用作 dict key) |
| Agent 的 KB 声明范围 | `agents.registry[].kb_refs` | `agent.kb_refs` | `dept.kb_refs` | — |
| 本次任务 KB 授权 | — | — | — | `packet.kb_refs` |
| KB 注册表 | `knowledge_bases[]` | `config.knowledge_bases` | — | — |
| Retriever 类型 | `knowledge_bases[].retriever` | `kb.retriever` | — | — |
| Retriever 配置 | `knowledge_bases[].config` | `kb.config` | — | — |
