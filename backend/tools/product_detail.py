"""Product detail page export tool."""

from __future__ import annotations

import html
from typing import Annotated, Any

from langchain_core.tools import tool

from tools.exports import _artifact, _parse_json_payload, _resolve_path


FONT_STACK = '-apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", "Helvetica Neue", Arial, sans-serif'


def _text(value: Any) -> str:
    return html.escape(str(value or "").strip(), quote=True)


def _clean_items(value: Any) -> list[dict]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _render_chips(spec: dict) -> str:
    chips = [_text(spec.get(key)) for key in ("category", "season") if _text(spec.get(key))]
    if not chips:
        return ""
    return '<div class="chips">' + "".join(f"<span>{chip}</span>" for chip in chips) + "</div>"


def _render_price(spec: dict) -> str:
    price = _text(spec.get("price"))
    original_price = _text(spec.get("original_price"))
    if not price and not original_price:
        return ""
    old = f'<span class="original-price">{original_price}</span>' if original_price else ""
    current = f'<span class="price">{price}</span>' if price else ""
    return f'<div class="price-row">{current}{old}</div>'


def _render_highlights(items: Any) -> str:
    cards = []
    for item in _clean_items(items)[:6]:
        title = _text(item.get("title"))
        desc = _text(item.get("desc"))
        icon = _text(item.get("icon"))
        if not (title or desc):
            continue
        cards.append(
            '<article class="highlight-card">'
            f'<div class="highlight-icon">{icon}</div>'
            f"<h3>{title}</h3>"
            f"<p>{desc}</p>"
            "</article>"
        )
    if not cards:
        return ""
    return f'<section><h2>核心卖点</h2><div class="highlight-grid">{"".join(cards)}</div></section>'


def _render_fabric(rows: Any) -> str:
    body = []
    for row in _clean_items(rows):
        label = _text(row.get("label"))
        value = _text(row.get("value"))
        if label or value:
            body.append(f"<tr><th>{label}</th><td>{value}</td></tr>")
    if not body:
        return ""
    return f'<section><h2>面料规格</h2><div class="table-wrap spec-table"><table><tbody>{"".join(body)}</tbody></table></div></section>'


def _render_size_table(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    headers = value.get("headers") or []
    rows = value.get("rows") or []
    if not isinstance(headers, list) or not isinstance(rows, list) or not headers or not rows:
        return ""

    header_html = "".join(f"<th>{_text(cell)}</th>" for cell in headers)
    row_html = []
    for row in rows:
        if not isinstance(row, list):
            continue
        cells = []
        for i, cell in enumerate(row):
            tag = "th" if i == 0 else "td"
            cells.append(f"<{tag}>{_text(cell)}</{tag}>")
        if cells:
            row_html.append(f"<tr>{''.join(cells)}</tr>")
    if not row_html:
        return ""

    note = _text(value.get("note"))
    note_html = f'<p class="note">{note}</p>' if note else ""
    return (
        "<section><h2>尺码表</h2>"
        f'<div class="table-wrap size-table"><table><thead><tr>{header_html}</tr></thead><tbody>{"".join(row_html)}</tbody></table></div>'
        f"{note_html}</section>"
    )


def _render_scenes(items: Any) -> str:
    cards = []
    for item in _clean_items(items)[:5]:
        title = _text(item.get("title"))
        desc = _text(item.get("desc"))
        if title or desc:
            cards.append(f'<article class="scene-card"><h3>{title}</h3><p>{desc}</p></article>')
    if not cards:
        return ""
    return f'<section><h2>搭配场景</h2><div class="scene-grid">{"".join(cards)}</div></section>'


def _render_care(items: Any) -> str:
    entries = []
    for item in _clean_items(items):
        text = _text(item.get("text"))
        icon = _text(item.get("icon"))
        if text:
            entries.append(f'<li><span class="care-icon">{icon}</span><span>{text}</span></li>')
    if not entries:
        return ""
    return f'<section><h2>洗护说明</h2><ul class="care-grid">{"".join(entries)}</ul></section>'


def _render_faq(items: Any) -> str:
    entries = []
    for item in _clean_items(items):
        question = _text(item.get("q"))
        answer = _text(item.get("a"))
        if question or answer:
            entries.append(f"<details><summary>{question}</summary><p>{answer}</p></details>")
    if not entries:
        return ""
    return f'<section><h2>FAQ</h2><div class="faq-list">{"".join(entries)}</div></section>'


def _render_footer(note: Any) -> str:
    text = _text(note)
    if not text:
        return ""
    return f'<footer><p>{text}</p></footer>'


def _html_document(spec: dict) -> str:
    product_name = _text(spec.get("product_name"))
    if not product_name:
        raise ValueError("spec_json.product_name is required")

    tagline = _text(spec.get("tagline"))
    title = product_name
    sections = [
        _render_highlights(spec.get("highlights")),
        _render_fabric(spec.get("fabric")),
        _render_size_table(spec.get("size_table")),
        _render_scenes(spec.get("scenes")),
        _render_care(spec.get("care")),
        _render_faq(spec.get("faq")),
    ]
    body_sections = "\n".join(section for section in sections if section)
    footer = _render_footer(spec.get("compliance_note"))

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    :root {{
      --primary: #1f2937;
      --accent: #a37e5c;
      --bg: #fafaf7;
      --surface: #ffffff;
      --subtle: #e5e3dc;
      --muted: #6b6b6b;
      --soft: #f1f0ea;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-width: 320px;
      background: var(--bg);
      color: var(--primary);
      font-family: {FONT_STACK};
      font-size: 16px;
      line-height: 1.65;
    }}
    .page {{
      width: min(100%, 880px);
      margin: 0 auto;
      padding: 44px 22px 56px;
    }}
    .hero {{
      padding: 58px 0 54px;
      border-bottom: 1px solid var(--subtle);
    }}
    .chips {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-bottom: 22px;
    }}
    .chips span {{
      display: inline-flex;
      align-items: center;
      min-height: 30px;
      padding: 4px 12px;
      border: 1px solid var(--subtle);
      border-radius: 999px;
      background: rgba(255,255,255,.72);
      color: var(--accent);
      font-size: 13px;
      font-weight: 650;
    }}
    h1 {{
      margin: 0;
      max-width: 760px;
      font-size: clamp(32px, 7vw, 40px);
      line-height: 1.14;
      letter-spacing: 0;
    }}
    .tagline {{
      margin: 18px 0 0;
      max-width: 620px;
      color: var(--muted);
      font-size: 18px;
    }}
    .price-row {{
      display: flex;
      align-items: baseline;
      gap: 14px;
      margin-top: 28px;
    }}
    .price {{
      color: var(--primary);
      font-size: 26px;
      font-weight: 750;
    }}
    .original-price {{
      color: var(--muted);
      font-size: 16px;
      text-decoration: line-through;
    }}
    section {{
      padding: 56px 0;
      border-bottom: 1px solid var(--subtle);
    }}
    h2 {{
      margin: 0 0 24px;
      font-size: 24px;
      line-height: 1.25;
      letter-spacing: 0;
    }}
    h3 {{
      margin: 0 0 8px;
      font-size: 17px;
      line-height: 1.35;
      letter-spacing: 0;
    }}
    p {{ margin: 0; }}
    .highlight-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 16px;
    }}
    .highlight-card, .scene-card, details {{
      border: 1px solid var(--subtle);
      border-radius: 12px;
      background: rgba(255,255,255,.78);
      box-shadow: 0 10px 28px rgba(31,41,55,.055);
    }}
    .highlight-card {{
      min-height: 190px;
      padding: 22px;
    }}
    .highlight-icon {{
      margin-bottom: 22px;
      font-size: 32px;
      line-height: 1;
    }}
    .highlight-card p, .scene-card p, details p, .note, footer {{
      color: var(--muted);
      font-size: 15px;
    }}
    .table-wrap {{
      overflow-x: auto;
      border: 1px solid var(--subtle);
      border-radius: 12px;
      background: var(--surface);
      box-shadow: 0 10px 28px rgba(31,41,55,.045);
    }}
    table {{
      width: 100%;
      min-width: 560px;
      border-collapse: collapse;
    }}
    th, td {{
      padding: 14px 16px;
      border-bottom: 1px solid var(--subtle);
      text-align: left;
      vertical-align: top;
      font-size: 15px;
    }}
    tr:last-child th, tr:last-child td {{ border-bottom: 0; }}
    .spec-table th {{
      width: 34%;
      font-weight: 750;
      background: var(--soft);
    }}
    .spec-table td {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
    }}
    .size-table thead th {{
      background: var(--primary);
      color: #fff;
      font-weight: 750;
    }}
    .size-table tbody tr:nth-child(even) {{ background: var(--soft); }}
    .size-table tbody th {{ font-weight: 750; }}
    .note {{
      margin-top: 12px;
    }}
    .scene-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 16px;
    }}
    .scene-card {{
      padding: 22px;
    }}
    .care-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
      margin: 0;
      padding: 0;
      list-style: none;
    }}
    .care-grid li {{
      display: flex;
      align-items: flex-start;
      gap: 12px;
      min-height: 64px;
      padding: 18px;
      border: 1px solid var(--subtle);
      border-radius: 12px;
      background: rgba(255,255,255,.78);
    }}
    .care-icon {{
      flex: 0 0 auto;
      font-size: 23px;
      line-height: 1.3;
    }}
    .faq-list {{
      display: grid;
      gap: 12px;
    }}
    details {{
      padding: 18px 20px;
    }}
    summary {{
      cursor: pointer;
      font-weight: 750;
      list-style-position: outside;
    }}
    details p {{
      margin-top: 12px;
    }}
    footer {{
      padding: 34px 0 0;
    }}
    @media (max-width: 760px) {{
      .page {{ padding: 30px 18px 42px; }}
      .hero {{ padding: 42px 0 44px; }}
      section {{ padding: 48px 0; }}
      .highlight-grid, .scene-grid, .care-grid {{
        grid-template-columns: 1fr;
      }}
      .highlight-card {{ min-height: 0; }}
      table {{ min-width: 520px; }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <section class="hero">
      {_render_chips(spec)}
      <h1>{product_name}</h1>
      {f'<p class="tagline">{tagline}</p>' if tagline else ''}
      {_render_price(spec)}
    </section>
    {body_sections}
    {footer}
  </main>
</body>
</html>
"""


@tool(response_format="content_and_artifact")
def create_product_detail_page(
    filename: Annotated[str, '文件名不带后缀，例如 "松林漫步-羊毛大衣-详情页"。强制 .html'],
    spec_json: Annotated[str, "JSON 对象，schema 见商品详情页工具说明"],
) -> tuple[str, dict]:
    """生成单文件 HTML 商品详情页，内联 CSS，浏览器直接打开即可看。"""
    spec = _parse_json_payload("spec_json", spec_json)
    if not isinstance(spec, dict):
        raise ValueError("spec_json must be a JSON object")

    content = _html_document(spec)
    path = _resolve_path(filename, "html")
    path.write_text(content, encoding="utf-8")
    artifact = _artifact(path, "html", {"chars": len(content), "product_name": str(spec.get("product_name", "")).strip()})
    msg = f"Wrote product detail HTML to {path} ({artifact['size_bytes']} bytes)."
    return msg, artifact
