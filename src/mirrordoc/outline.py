"""Human-readable outline of a parsed document.

Used by ``mirrordoc outline`` so authors can eyeball the exact skeleton the
comparison engine sees — handy when a finding looks surprising.
"""

from __future__ import annotations

from collections import Counter
from typing import List

from .mdparse import Document


def summary_counts(doc: Document) -> str:
    """One-line block census: ``12 code blocks (bash x6, text x4); 2 tables ...``."""
    langs = Counter(cb.lang or "plain" for cb in doc.code_blocks)
    lang_bits = ", ".join(f"{lang} x{n}" for lang, n in sorted(langs.items()))
    code = f"{len(doc.code_blocks)} code blocks"
    if lang_bits:
        code += f" ({lang_bits})"
    shapes = ", ".join(f"{t.columns}x{t.rows}" for t in doc.tables)
    tables = f"{len(doc.tables)} tables"
    if shapes:
        tables += f" ({shapes})"
    return (
        f"{code}; {tables}; {len(doc.links)} links; "
        f"{len(doc.images)} images; {len(doc.list_items)} list items"
    )


def render_outline(label: str, doc: Document) -> str:
    """Render the heading tree plus the block census for one file."""
    lines: List[str] = [f"{label} — {doc.line_count} lines"]
    if not doc.headings:
        lines.append("  (no headings)")
    for h in doc.headings:
        indent = "  " * h.level
        title = h.text or "(untitled)"
        lines.append(f"{indent}H{h.level} {title}  (L{h.line})")
    lines.append(f"  {summary_counts(doc)}")
    return "\n".join(lines)
