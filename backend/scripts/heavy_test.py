"""Heavy end-to-end test: PPT-style multi-department task.

Captures:
  - All HTTP request/response bodies to the proxy (via httpx event hooks)
  - All run_step + checklist_sync events emitted by the workflow
  - The final OrcSessionState (artifacts, shards, checklist)
  - All checkpoint rows written to the SQLite checkpointer
  - WorldState snapshots seen by lead and by each worker

Run with the venv:
  "/Users/niuniu/Desktop/boxcc 1.0/.venv/bin/python" backend/scripts/heavy_test.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
from contextlib import AsyncExitStack
from pathlib import Path

# Patch httpx BEFORE any langchain/openai import so the event hooks attach to
# the same Client instance the SDK uses.
import httpx

_REQUESTS: list[dict] = []
_RESPONSES: list[dict] = []


_orig_sync_init = httpx.Client.__init__
_orig_async_init = httpx.AsyncClient.__init__


def _patched_sync_init(self, *args, **kwargs):
    hooks = kwargs.get("event_hooks") or {}
    hooks.setdefault("request", []).append(_capture_request)
    hooks.setdefault("response", []).append(_capture_response)
    kwargs["event_hooks"] = hooks
    return _orig_sync_init(self, *args, **kwargs)


def _patched_async_init(self, *args, **kwargs):
    hooks = kwargs.get("event_hooks") or {}
    hooks.setdefault("request", []).append(_acapture_request)
    hooks.setdefault("response", []).append(_acapture_response)
    kwargs["event_hooks"] = hooks
    return _orig_async_init(self, *args, **kwargs)


def _capture_request(req: httpx.Request) -> None:
    if "ikuncode" not in str(req.url):
        return
    try:
        body = json.loads(req.content) if req.content else None
    except Exception:
        body = repr(req.content[:200])
    _REQUESTS.append({
        "ts": time.time(),
        "url": str(req.url),
        "method": req.method,
        "body": body,
    })


def _capture_response(resp: httpx.Response) -> None:
    if "ikuncode" not in str(resp.url):
        return
    resp.read()
    try:
        data = json.loads(resp.content) if resp.content else None
    except Exception:
        data = repr(resp.content[:200])
    _RESPONSES.append({
        "ts": time.time(),
        "url": str(resp.url),
        "status": resp.status_code,
        "body": data,
    })


async def _acapture_request(req: httpx.Request) -> None:
    _capture_request(req)


async def _acapture_response(resp: httpx.Response) -> None:
    if "ikuncode" not in str(resp.url):
        return
    await resp.aread()
    try:
        data = json.loads(resp.content) if resp.content else None
    except Exception:
        data = repr(resp.content[:200])
    _RESPONSES.append({
        "ts": time.time(),
        "url": str(resp.url),
        "status": resp.status_code,
        "body": data,
    })


httpx.Client.__init__ = _patched_sync_init  # type: ignore[assignment]
httpx.AsyncClient.__init__ = _patched_async_init  # type: ignore[assignment]


# Set up data dir and env BEFORE importing app modules so paths resolve fresh.
_TMP = tempfile.mkdtemp(prefix="boxcc-heavy-")
os.environ["BOXCC_BACKEND_DATA_DIR"] = _TMP
print(f"[setup] data dir: {_TMP}")

# Make backend root importable.
_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_BACKEND / ".env")

from agents.lead_agent import make_lead_agent  # noqa: E402
from config.app_config import get_app_config  # noqa: E402
from config.paths import get_data_dir  # noqa: E402
from langchain_core.messages import HumanMessage  # noqa: E402
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver  # noqa: E402
from runtime_events import reset_event_emitter, set_event_emitter  # noqa: E402
from session.store import get_session_store  # noqa: E402
from subagents.workflow import set_delegate_checkpointer  # noqa: E402


# Point the session store at our temp data dir by resetting the singleton.
import session.store as _store_mod  # noqa: E402

_store_mod._STORE = None
_store_mod.SessionStore.__init__.__defaults__  # touch class
# Override the default path resolution to use the temp dir for this run.
orig_get = _store_mod.get_session_store


def _override_store():
    if _store_mod._STORE is None:
        _store_mod._STORE = _store_mod.SessionStore(Path(_TMP) / "orc_sessions.json")
    return _store_mod._STORE


_store_mod.get_session_store = _override_store
get_session_store = _override_store

# Modules that imported get_session_store before this override keep their own
# function reference; patch them too so the whole e2e run is isolated.
import agents.middlewares.world_state_middleware as _world_state_mod  # noqa: E402
import session as _session_pkg  # noqa: E402
import session.checklist as _checklist_mod  # noqa: E402

_world_state_mod.get_session_store = _override_store
_checklist_mod.get_session_store = _override_store
_session_pkg.get_session_store = _override_store


_EVENTS: list[dict] = []


async def _emitter(payload: dict) -> None:
    _EVENTS.append(payload)


PPT_TASK = (
    "做一份 Q3 商品复盘 PPT，看滞销 + 补货 + 价格策略。"
    "请输出真实 .pptx 文件，最终把 PPT 文件路径放在回复里。"
)


async def run() -> dict:
    print(f"[setup] models in config: {[m.name for m in get_app_config().models]}")

    async with AsyncExitStack() as stack:
        ckp_path = get_data_dir() / "checkpoints.db"
        saver = await stack.enter_async_context(
            AsyncSqliteSaver.from_conn_string(str(ckp_path))
        )
        set_delegate_checkpointer(saver)
        print(f"[setup] checkpointer attached at {ckp_path}")

        session_id = "heavy-1"
        message_id = "msg-heavy-1"

        # Seed the session row so WorldStateMiddleware has something to render.
        get_session_store().get_or_create(session_id, user_goal=PPT_TASK)

        tokens = set_event_emitter(
            _emitter,
            message_id=message_id,
            session_id=session_id,
            turn_id=message_id,
        )
        t0 = time.time()
        error: str | None = None
        content = ""
        try:
            agent = make_lead_agent()
            result = await agent.ainvoke(
                {"messages": [HumanMessage(content=PPT_TASK)]},
                config={"configurable": {"thread_id": session_id}, "recursion_limit": 80},
            )
            ai_msgs = [
                m for m in result.get("messages", [])
                if getattr(m, "type", None) == "ai" and getattr(m, "content", None)
            ]
            content = ai_msgs[-1].content if ai_msgs else ""
            if isinstance(content, list):
                content = " | ".join(str(b) for b in content)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            print(f"[run] ERROR: {error}")
        finally:
            reset_event_emitter(tokens)
        elapsed = time.time() - t0
        print(f"[run] complete in {elapsed:.1f}s, answer_len={len(content)}, error={error}")
        return {"final": str(content), "elapsed_s": elapsed, "ckp_path": str(ckp_path), "error": error}


def summarize_events(events: list[dict]) -> dict:
    by_type: dict[str, int] = {}
    by_step: dict[str, list[str]] = {}
    for e in events:
        t = e.get("type", "?")
        by_type[t] = by_type.get(t, 0) + 1
        if t == "run_step":
            sid = e.get("step_id", "?")
            by_step.setdefault(sid, []).append(e.get("status", "?"))
    return {"by_type": by_type, "step_status_transitions": by_step}


def summarize_session(session_id: str) -> dict:
    sess_file = Path(_TMP) / "orc_sessions.json"
    if not sess_file.exists():
        return {"missing_file": str(sess_file)}
    with open(sess_file) as f:
        data = json.load(f)
    sess = data.get(session_id, {})
    return {
        "task_type": sess.get("task_type"),
        "last_run_status": sess.get("last_run_status"),
        "selected_workers": sess.get("selected_workers"),
        "checklist": [
            {"item_id": it["item_id"], "owner": it["owner"], "status": it["status"]}
            for it in sess.get("execution_checklist", [])
        ],
        "worker_shards": {
            wid: {
                "status": s["status"],
                "retry_count": s["retry_count"],
                "last_attempt": s["last_attempt"],
                "result_summary_head": (s.get("result_summary") or "")[:140],
            }
            for wid, s in sess.get("worker_shards", {}).items()
        },
        "shared_artifacts": [
            {"artifact_id": a["artifact_id"], "owner": a["owner"], "kind": a["kind"], "content_head": (a.get("content") or "")[:120]}
            for a in sess.get("shared_artifacts", [])
        ],
        "validation_report": sess.get("latest_validation_report"),
    }


def summarize_checkpoints(db_path: str) -> dict:
    import sqlite3
    con = sqlite3.connect(db_path)
    rows = con.execute(
        "SELECT thread_id, checkpoint_id, parent_checkpoint_id FROM checkpoints ORDER BY thread_id, checkpoint_id"
    ).fetchall()
    threads: dict[str, list[dict]] = {}
    for tid, cid, pid in rows:
        threads.setdefault(tid, []).append({"checkpoint_id": cid, "parent": pid})
    return {"thread_count": len(threads), "threads": {k: len(v) for k, v in threads.items()}, "sample_chain": threads}


def summarize_proxy_io(requests: list[dict], responses: list[dict]) -> dict:
    if not requests:
        return {"request_count": 0}
    by_agent: dict[str, list[dict]] = {}
    for req in requests:
        body = req.get("body") or {}
        if not isinstance(body, dict):
            continue
        msgs = body.get("messages") or []
        sys_msgs = [m.get("content", "") for m in msgs if m.get("role") == "system"]
        # Try to identify the worker by the lead-or-worker system prompt header.
        agent_id = "?"
        for sm in sys_msgs:
            if isinstance(sm, str):
                if "id: orc" in sm or "name: 主席团" in sm or "lead orchestrator" in sm.lower():
                    agent_id = "orc"
                    break
                for token in ("biz_legal", "biz_fin", "biz_it", "biz_voc", "biz_bi",
                              "gro_brand", "gro_pr", "gro_content",
                              "mer_plan", "mer_ops",
                              "sup_buy", "sup_pmc", "sup_qc", "sup_wms",
                              "chl_ch", "chl_store", "chl_ec",
                              "crt"):
                    if token in sm:
                        agent_id = token
                        break
                if agent_id != "?":
                    break
        by_agent.setdefault(agent_id, []).append({
            "model": body.get("model"),
            "msg_count": len(msgs),
            "system_msg_count": len(sys_msgs),
            "user_msg_len": sum(len(m.get("content") or "") for m in msgs if m.get("role") == "user"),
            "tools": len(body.get("tools") or []),
        })
    sampled_request = requests[0]
    body = sampled_request.get("body") or {}
    sample_world_state = None
    sample_memory_core = None
    if isinstance(body, dict):
        for m in body.get("messages") or []:
            content = m.get("content")
            if isinstance(content, str):
                if "<world_state" in content and sample_world_state is None:
                    sample_world_state = content[:400]
                if "<memory:core" in content and sample_memory_core is None:
                    sample_memory_core = content[:400]
    return {
        "request_count": len(requests),
        "response_count": len(responses),
        "by_agent": by_agent,
        "first_request_url": requests[0]["url"],
        "first_response_status": responses[0]["status"] if responses else None,
        "sample_world_state_head": sample_world_state,
        "sample_memory_core_head": sample_memory_core,
    }


def main() -> None:
    result: dict = {"final": "", "elapsed_s": 0.0, "ckp_path": str(Path(_TMP) / "checkpoints.db"), "error": "did-not-run"}
    try:
        result = asyncio.run(run())
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        print(f"[run] outer error: {result['error']}")
    finally:
        # Always dump raw capture, even if the run crashed.
        raw_path = Path(_TMP) / "raw_capture.json"
        try:
            raw_path.write_text(json.dumps({
                "events": _EVENTS[:200],
                "requests": _REQUESTS,
                "responses": _RESPONSES,
            }, ensure_ascii=False, indent=2))
            print(f"[dump] raw capture: {raw_path} (requests={len(_REQUESTS)}, responses={len(_RESPONSES)})")
        except Exception as exc:
            print(f"[dump] failed to write raw capture: {exc}")

    def _safe(label, fn):
        try:
            return fn()
        except Exception as exc:
            return {"error": f"{type(exc).__name__}: {exc}"}

    report = {
        "elapsed_s": result["elapsed_s"],
        "error": result.get("error"),
        "final_answer_head": result["final"][:600],
        "final_answer_length": len(result["final"]),
        "events_summary": _safe("events", lambda: summarize_events(_EVENTS)),
        "session_state": _safe("session", lambda: summarize_session("heavy-1")),
        "checkpoints": _safe("checkpoints", lambda: summarize_checkpoints(result["ckp_path"])),
        "proxy_io": _safe("proxy_io", lambda: summarize_proxy_io(_REQUESTS, _RESPONSES)),
    }

    out_path = Path(_TMP) / "heavy_test_report.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    raw_path = Path(_TMP) / "raw_capture.json"
    raw_path.write_text(json.dumps({
        "events": _EVENTS[:200],
        "requests": _REQUESTS,
        "responses": _RESPONSES,
    }, ensure_ascii=False, indent=2))

    print("\n=== REPORT ===")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\n[done] full report: {out_path}")
    print(f"[done] raw capture: {raw_path}")


if __name__ == "__main__":
    main()
