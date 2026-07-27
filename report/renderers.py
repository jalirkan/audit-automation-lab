"""Markdown and standalone-HTML renderers over the block model.

The HTML embeds its own CSS and fetches nothing: an audit artifact that
pulls a stylesheet from a CDN renders differently — or not at all — opened
from an archive years later (toolkit D-029). A test asserts no http://,
https://, <script or <link appears in output. Both renderers refuse
conclusory language before emitting anything.
"""

import html as _html

from report.document import Document, Heading, KeyValues, ListBlock, Paragraph, Table
from report.language import guard_document


def render_markdown(doc: Document) -> str:
    guard_document(doc)
    out = [f"# {_md_escape(doc.title)}", ""]
    for b in doc.blocks:
        if isinstance(b, Heading):
            out.append("#" * max(2, min(6, b.level)) + " " + _md_escape(b.text))
            out.append("")
        elif isinstance(b, Paragraph):
            out.append(_md_escape(b.text))
            out.append("")
        elif isinstance(b, KeyValues):
            out.append("| | |")
            out.append("|---|---|")
            for k, v in b.items:
                out.append(f"| {_md_cell(k)} | {_md_cell(v)} |")
            out.append("")
        elif isinstance(b, Table):
            if b.caption:
                out.append(f"*{_md_escape(b.caption)}*")
                out.append("")
            out.append("| " + " | ".join(_md_cell(h) for h in b.headers) + " |")
            out.append("|" + "---|" * len(b.headers))
            for row in b.rows:
                out.append("| " + " | ".join(_md_cell(c) for c in row) + " |")
            out.append("")
        elif isinstance(b, ListBlock):
            for item in b.items:
                out.append(f"- {_md_escape(str(item))}")
            out.append("")
    return "\n".join(out).rstrip() + "\n"


def _md_escape(text) -> str:
    return str(text)


def _md_cell(text) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


_CSS = """
body { font-family: Georgia, 'Times New Roman', serif; margin: 2.5rem auto;
       max-width: 60rem; color: #1a1a1a; line-height: 1.45; }
h1 { font-size: 1.5rem; border-bottom: 2px solid #1a1a1a; padding-bottom: .3rem; }
h2 { font-size: 1.15rem; margin-top: 1.6rem; }
h3 { font-size: 1.0rem; }
table { border-collapse: collapse; margin: .6rem 0 1rem; min-width: 40rem; }
th, td { border: 1px solid #999; padding: .25rem .5rem; text-align: left;
         font-size: .85rem; vertical-align: top; }
th { background: #efefef; }
.kv td:first-child { font-weight: bold; width: 18rem; }
.outcome-pass { color: #1b5e20; }
.outcome-exception { color: #b71c1c; }
.outcome-inconclusive { color: #795548; }
"""


def render_html(doc: Document) -> str:
    guard_document(doc)
    e = _html.escape
    body = [f"<h1>{e(doc.title)}</h1>"]
    for b in doc.blocks:
        if isinstance(b, Heading):
            level = max(2, min(6, b.level))
            body.append(f"<h{level}>{e(b.text)}</h{level}>")
        elif isinstance(b, Paragraph):
            body.append(f"<p>{e(b.text)}</p>")
        elif isinstance(b, KeyValues):
            rows = "".join(
                f"<tr><td>{e(str(k))}</td><td>{_outcome_span(e(str(v)))}</td></tr>"
                for k, v in b.items
            )
            body.append(f'<table class="kv">{rows}</table>')
        elif isinstance(b, Table):
            head = "".join(f"<th>{e(str(h))}</th>" for h in b.headers)
            rows = "".join(
                "<tr>"
                + "".join(f"<td>{_outcome_span(e(str(c)))}</td>" for c in row)
                + "</tr>"
                for row in b.rows
            )
            caption = f"<caption>{e(b.caption)}</caption>" if b.caption else ""
            body.append(
                f"<table>{caption}<tr>{head}</tr>{rows}</table>"
            )
        elif isinstance(b, ListBlock):
            items = "".join(f"<li>{e(str(i))}</li>" for i in b.items)
            body.append(f"<ul>{items}</ul>")
    return (
        "<!DOCTYPE html>\n<html>\n<head>\n<meta charset=\"utf-8\">\n"
        f"<title>{e(doc.title)}</title>\n<style>{_CSS}</style>\n</head>\n<body>\n"
        + "\n".join(body)
        + "\n</body>\n</html>\n"
    )


def _outcome_span(escaped_text: str) -> str:
    """Colour bare outcome words in cells; purely cosmetic."""
    if escaped_text in ("pass", "exception", "inconclusive"):
        return f'<span class="outcome-{escaped_text}">{escaped_text}</span>'
    return escaped_text
