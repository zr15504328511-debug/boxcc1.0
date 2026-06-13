"""Producer layer — assemble worker outputs into a strict deliverable spec.

The producer is NOT a tool-calling agent. It is a single structured-output
LLM call wrapped by a workflow node (`run_producer` in `workflow.py`):

    deliverable_type_id  →  pick (pydantic model, export tool)
    render template brief + worker outputs + user question
    model.with_structured_output(Model, method="function_calling")  →  validated obj
    to_payload(obj)  →  export_tool.func(filename, <payload_arg>)  →  file on disk

`method="function_calling"` is mandatory: the ikuncode proxy rejects strict
`json_schema` for discriminated unions (400 'oneOf' is not permitted), but
accepts the same schemas via function calling. See `tools/specs.py`.

Reliability strategy: pydantic validates the shape; a single retry feeds the
error back to the model; if it still fails we return `{"error": ...}` so the
workflow can degrade to a text-only answer instead of crashing the turn.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Callable

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from agents.spec_loader import load_prompt_spec
from models.factory import create_chat_model
from tools import (
    create_docx,
    create_management_ppt,
    create_product_detail_page,
    create_xlsx,
)
from tools.specs import (
    DeckSpec,
    DocSpec,
    ProductSpec,
    WorkbookSpec,
    deck_to_payload,
    doc_to_payload,
    product_to_payload,
    workbook_to_payload,
)

logger = logging.getLogger(__name__)

_PRODUCER_SPEC_PATH = "agentspecs/producer.md"
_PRODUCER_FALLBACK_PROMPT = (
    "You assemble completed worker outputs into a strict, structured "
    "deliverable spec that matches the given template. Do not invent data; "
    "use [数据待填] for missing required slots. Follow the template structure, "
    "required sections, counts, notes, and voice exactly."
)

# Keep the producer's user message under the ikuncode ~16K body limit.
_MAX_USER_CHARS = 13000


@dataclass(frozen=True)
class ProducerSpec:
    """Wiring for one deliverable type: schema → payload → export tool."""
    model: type[BaseModel]
    export_tool: Any                      # a LangChain StructuredTool (we call .func)
    to_payload: Callable[[Any], dict]     # validated model → export tool content kwargs


def _doc(model: type[BaseModel] = DocSpec) -> ProducerSpec:
    """Shorthand for the shared long-form-document pipeline (→ create_docx)."""
    return ProducerSpec(model=model, export_tool=create_docx, to_payload=doc_to_payload)


# Keyed by deliverable_type_id (NOT output_tool) so several types can share a
# generic tool (create_docx / create_xlsx) with the same schema.
PRODUCER_REGISTRY: dict[str, ProducerSpec] = {
    # Visual / structured deliverables (own schema + tool)
    "management_ppt": ProducerSpec(DeckSpec, create_management_ppt, deck_to_payload),
    "product_detail_page": ProducerSpec(ProductSpec, create_product_detail_page, product_to_payload),
    "inventory_report": ProducerSpec(WorkbookSpec, create_xlsx, workbook_to_payload),
    # Group A — strategy / planning documents (shared DocSpec → create_docx)
    "brand_positioning": _doc(),
    "user_persona": _doc(),
    "trend_report": _doc(),
    "competitor_analysis": _doc(),
    "merchandising_plan": _doc(),
}


def build_producer_system_prompt() -> str:
    """Load the producer constitution. Lean by design — no master prompt."""
    return load_prompt_spec(_PRODUCER_SPEC_PATH, _PRODUCER_FALLBACK_PROMPT)


def _build_user_message(*, brief: str, worker_summary: str, user_question: str) -> str:
    """Assemble the producer's input, trimming worker output to fit budget."""
    # Per-worker trim first (reuse the critic-side guardrail), then an overall
    # cap so brief + question always fit.
    from subagents.workflow import _truncate_worker_summary

    worker_summary = _truncate_worker_summary(worker_summary)
    head = (
        f"[用户原始问题]\n{user_question}\n\n"
        f"{brief}\n\n"
        "[部门产出 — 按 owner 标注，这是你组装产物的唯一素材来源]\n"
    )
    budget = _MAX_USER_CHARS - len(head)
    if budget < 1000:
        budget = 1000
    if len(worker_summary) > budget:
        worker_summary = worker_summary[: budget - 40].rstrip() + "\n...[内容已截断以适配预算]..."
    return head + worker_summary


def _invoke_structured(model_cls: type[BaseModel], system_prompt: str, user_message: str):
    """Synchronous structured-output call (run via asyncio.to_thread)."""
    model = create_chat_model(temperature=0.4)
    structured = model.with_structured_output(model_cls, method="function_calling")
    return structured.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message),
    ])


async def produce_deliverable(
    *,
    deliverable_type_id: str,
    worker_summary: str,
    user_question: str,
    attempt_number: int = 1,
) -> dict[str, Any]:
    """Assemble + export one deliverable.

    Returns `{"artifact": <export artifact dict>}` on success, or
    `{"error": <message>}` on failure (after one retry).
    """
    spec = PRODUCER_REGISTRY.get(deliverable_type_id)
    if spec is None:
        return {"error": f"no producer registered for '{deliverable_type_id}'"}

    from deliverables.registry import render_deliverable_brief

    brief = render_deliverable_brief(deliverable_type_id)
    system_prompt = build_producer_system_prompt()
    user_message = _build_user_message(
        brief=brief, worker_summary=worker_summary, user_question=user_question
    )

    obj: BaseModel | None = None
    last_error: str = ""
    for attempt in range(2):  # one initial try + one retry
        try:
            obj = await asyncio.to_thread(
                _invoke_structured, spec.model, system_prompt, user_message
            )
            break
        except Exception as exc:  # proxy error or pydantic validation failure
            last_error = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "producer structured-output attempt %d failed for %s: %s",
                attempt + 1, deliverable_type_id, last_error,
            )
            user_message = (
                user_message
                + f"\n\n[上次失败原因]\n{last_error}\n请修正后严格按 schema 重新输出。"
            )

    if obj is None:
        return {"error": f"structured output failed: {last_error}"}

    try:
        payload = spec.to_payload(obj)  # dict of content kwargs for the export tool
        filename = f"{deliverable_type_id}-attempt{attempt_number}"
        # Call the raw function so we get back (content, artifact); .invoke()
        # would surface only the content string.
        _msg, artifact = spec.export_tool.func(filename=filename, **payload)
        return {"artifact": artifact}
    except Exception as exc:
        err = f"export failed: {type(exc).__name__}: {exc}"
        logger.warning("producer export failed for %s: %s", deliverable_type_id, err)
        return {"error": err}
