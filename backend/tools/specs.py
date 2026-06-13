"""Pydantic spec models for the producer layer.

These mirror, field-for-field, the JSON shapes the export tools in
`tools/exports.py`, `tools/management_ppt.py`, and `tools/product_detail.py`
already consume. The producer (see `subagents/producer.py`) asks the LLM for
one of these models via `with_structured_output(..., method="function_calling")`
— pydantic then validates the shape before we hand it to the export tool.

Why function_calling and not json_schema: the ikuncode proxy rejects the
strict `json_schema` mode for discriminated unions ("'oneOf' is not
permitted", 400). function_calling accepts the same nested/union schemas, so
we get strong typing (which slides, which blocks, required fields) without the
strict-mode restriction. Verified end-to-end against gpt-5.5 on the proxy.

Each spec ships a `to_payload(obj)` helper that converts the validated model
into exactly the argument value its export tool expects (a JSON string for the
json-string tools, raw markdown for `create_markdown`).
"""

import json
from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, Field


def _dump_json(model: BaseModel) -> str:
    """Compact, unicode-preserving JSON for the json-string export tools."""
    return json.dumps(model.model_dump(exclude_none=True), ensure_ascii=False)


# ===========================================================================
# DeckSpec  →  create_management_ppt(deck_json=...)
# ===========================================================================

class DeckMeta(BaseModel):
    title: str
    subtitle: Optional[str] = None
    author: Optional[str] = None
    date: Optional[str] = None
    brand: Optional[str] = None
    theme: Optional[Literal["editorial", "cool", "warm"]] = None


# ---- content-slide blocks (discriminated on `type`) ----

class BulletsBlock(BaseModel):
    type: Literal["bullets"]
    items: list[str]


class CardItem(BaseModel):
    title: str
    desc: str = ""


class CardsBlock(BaseModel):
    type: Literal["cards"]
    items: list[CardItem]  # renderer shows up to 4


class CalloutBlock(BaseModel):
    type: Literal["callout"]
    text: str


class ParagraphBlock(BaseModel):
    type: Literal["paragraph"]
    text: str


class KVItem(BaseModel):
    label: str
    value: str


class KVBlock(BaseModel):
    type: Literal["kv"]
    items: list[KVItem]


ContentBlock = Annotated[
    Union[BulletsBlock, CardsBlock, CalloutBlock, ParagraphBlock, KVBlock],
    Field(discriminator="type"),
]


# ---- chart payload for data slides ----

class ChartSpec(BaseModel):
    type: Literal["bar", "line", "pie"] = "bar"
    title: Optional[str] = None
    categories: list[str] = Field(default_factory=list)
    # bar/line: {series_name: [values]}; pie uses labels+values instead
    series: Optional[dict[str, list[float]]] = None
    labels: Optional[list[str]] = None
    values: Optional[list[float]] = None


# ---- closing-slide action item ----

class ActionItem(BaseModel):
    owner: str = ""
    action: str
    due: str = ""


# ---- the six slide types (discriminated on `type`) ----

class CoverSlide(BaseModel):
    type: Literal["cover"]
    title: str
    subtitle: Optional[str] = None
    eyebrow: Optional[str] = None
    author: Optional[str] = None
    date: Optional[str] = None
    notes: Optional[str] = None


class AgendaSlide(BaseModel):
    type: Literal["agenda"]
    title: str = "本次议程"
    items: list[str]
    notes: Optional[str] = None


class DividerSlide(BaseModel):
    type: Literal["divider"]
    title: str
    number: Optional[str] = None  # auto-numbered if omitted
    intro: Optional[str] = None
    notes: Optional[str] = None


class ContentSlide(BaseModel):
    type: Literal["content"]
    title: str
    eyebrow: Optional[str] = None
    lead: Optional[str] = None  # one-sentence takeaway
    blocks: list[ContentBlock] = Field(default_factory=list)
    notes: Optional[str] = None


class DataSlide(BaseModel):
    type: Literal["data"]
    title: str
    eyebrow: Optional[str] = None
    takeaway: Optional[str] = None
    chart: ChartSpec
    notes: Optional[str] = None


class ClosingSlide(BaseModel):
    type: Literal["closing"]
    title: str = "下一步与决策"
    actions: list[ActionItem] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    notes: Optional[str] = None


Slide = Annotated[
    Union[CoverSlide, AgendaSlide, DividerSlide, ContentSlide, DataSlide, ClosingSlide],
    Field(discriminator="type"),
]


class DeckSpec(BaseModel):
    meta: DeckMeta
    slides: list[Slide]


def deck_to_payload(deck: DeckSpec) -> str:
    return _dump_json(deck)


# ===========================================================================
# ProductSpec  →  create_product_detail_page(spec_json=...)
# ===========================================================================

class Highlight(BaseModel):
    icon: str = ""
    title: str
    desc: str = ""


class FabricRow(BaseModel):
    label: str
    value: str


class SizeTable(BaseModel):
    headers: list[str]
    rows: list[list[str]]
    note: Optional[str] = None


class Scene(BaseModel):
    title: str
    desc: str = ""


class CareItem(BaseModel):
    icon: str = ""
    text: str


class FaqItem(BaseModel):
    q: str
    a: str


class ProductSpec(BaseModel):
    product_name: str
    tagline: Optional[str] = None
    category: Optional[str] = None
    season: Optional[str] = None
    price: Optional[str] = None
    original_price: Optional[str] = None
    highlights: list[Highlight] = Field(default_factory=list)
    fabric: list[FabricRow] = Field(default_factory=list)
    size_table: Optional[SizeTable] = None
    scenes: list[Scene] = Field(default_factory=list)
    care: list[CareItem] = Field(default_factory=list)
    faq: list[FaqItem] = Field(default_factory=list)
    compliance_note: Optional[str] = None


def product_to_payload(product: ProductSpec) -> str:
    return _dump_json(product)


# ===========================================================================
# WorkbookSpec  →  create_xlsx(sheets_json=...)
# ===========================================================================

class SheetSpec(BaseModel):
    name: str
    headers: list[str] = Field(default_factory=list)
    # cells may be strings, numbers, booleans, or null (function_calling
    # tolerates Any; create_xlsx coerces non-scalars to str)
    rows: list[list[Any]] = Field(default_factory=list)


class WorkbookSpec(BaseModel):
    sheets: list[SheetSpec]


def workbook_to_payload(workbook: WorkbookSpec) -> str:
    return json.dumps(
        [s.model_dump(exclude_none=True) for s in workbook.sheets],
        ensure_ascii=False,
    )


# ===========================================================================
# NoteSpec  →  create_markdown(content=...)  [xhs_note]
# ===========================================================================

class NoteSpec(BaseModel):
    title: str
    hook: str
    pain_points: list[str]
    product_intro: str
    try_on: str
    outfit_combos: list[str]
    tips: list[str] = Field(default_factory=list)
    hashtags: list[str]
    compliance_note: str


def render_note_markdown(note: NoteSpec) -> str:
    """Deterministically assemble a NoteSpec into the 9-section xhs markdown."""
    lines: list[str] = [f"# {note.title.strip()}", "", note.hook.strip(), ""]

    if note.pain_points:
        lines.append("## 你是不是也有这些困扰")
        lines.extend(f"- {p.strip()}" for p in note.pain_points)
        lines.append("")

    lines.append("## 产品介绍")
    lines.append(note.product_intro.strip())
    lines.append("")

    lines.append("## 真实试穿")
    lines.append(note.try_on.strip())
    lines.append("")

    if note.outfit_combos:
        lines.append("## 搭配场景")
        lines.extend(f"- {c.strip()}" for c in note.outfit_combos)
        lines.append("")

    if note.tips:
        lines.append("## 小贴士 / 避雷")
        lines.extend(f"- {t.strip()}" for t in note.tips)
        lines.append("")

    if note.hashtags:
        tags = " ".join(
            ("#" + h.strip().lstrip("#")) for h in note.hashtags if h.strip()
        )
        lines.append(tags)
        lines.append("")

    lines.append(f"> {note.compliance_note.strip()}")
    return "\n".join(lines).strip() + "\n"


def note_to_payload(note: NoteSpec) -> str:
    return render_note_markdown(note)
