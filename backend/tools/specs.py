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


def deck_to_payload(deck: DeckSpec) -> dict:
    return {"deck_json": _dump_json(deck)}


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


def product_to_payload(product: ProductSpec) -> dict:
    return {"spec_json": _dump_json(product)}


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


def workbook_to_payload(workbook: WorkbookSpec) -> dict:
    return {
        "sheets_json": json.dumps(
            [s.model_dump(exclude_none=True) for s in workbook.sheets],
            ensure_ascii=False,
        )
    }


# ===========================================================================
# DocSpec  →  create_docx(title=..., sections_json=...)
# ===========================================================================
# Long-form professional documents (品牌定位 / 用户画像 / 趋势报告 /
# 竞品分析 / 季度商品企划 / 客服FAQ知识库 / 培训资料 …) all share this one
# shape: an ordered list of headed sections with paragraph bodies. Express
# bullet points as paragraphs prefixed with "· "; create_docx renders each
# paragraph as its own block.

class DocSection(BaseModel):
    heading: str
    level: int = 1  # 1–3 (clamped by create_docx)
    paragraphs: list[str] = Field(default_factory=list)


class DocSpec(BaseModel):
    title: str
    sections: list[DocSection]


def doc_to_payload(doc: DocSpec) -> dict:
    return {
        "title": doc.title,
        "sections_json": json.dumps(
            [s.model_dump() for s in doc.sections], ensure_ascii=False
        ),
    }
