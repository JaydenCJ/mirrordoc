"""Structure comparison between a canonical document and a translated mirror.

The contract a mirror must honor: same heading skeleton, byte-identical code
blocks, same table shapes, same link destinations, same images. Prose is free
to differ — that is the translation. Every violation becomes a
:class:`Finding` with a stable machine-readable ``code``.
"""

from __future__ import annotations

import fnmatch
import posixpath
import re
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import List, Optional, Sequence, Tuple

from .mdparse import Document

SEVERITIES = ("error", "warning", "info")


@dataclass(frozen=True)
class Finding:
    """One detected divergence between source and mirror."""

    code: str
    severity: str  # "error" | "warning" | "info"
    message: str
    source_line: Optional[int] = None
    mirror_line: Optional[int] = None


@dataclass(frozen=True)
class CompareOptions:
    """Tunables for :func:`compare`; defaults match the CLI defaults."""

    lang: str = ""  # mirror language tag, for localized-link equivalence
    compare_code_content: bool = True
    check_anchors: bool = False
    ignore_links: Tuple[str, ...] = ()


def _q(text: str, limit: int = 60) -> str:
    """Quote heading/link text for messages, ellipsized to keep lines short."""
    t = " ".join(text.split())
    if len(t) > limit:
        t = t[: limit - 1] + "…"
    return f'"{t}"'


# -- headings ----------------------------------------------------------------


def _compare_headings(src: Document, mir: Document, out: List[Finding]) -> None:
    a = [h.level for h in src.headings]
    b = [h.level for h in mir.headings]
    sm = SequenceMatcher(None, a, b, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        if tag in ("delete", "replace"):
            for k in range(i1 + (j2 - j1 if tag == "replace" else 0), i2):
                h = src.headings[k]
                out.append(
                    Finding(
                        code="heading-missing",
                        severity="error",
                        message=(
                            f"mirror is missing a level-{h.level} heading: "
                            f"{_q(h.text)} (source L{h.line})"
                        ),
                        source_line=h.line,
                    )
                )
        if tag in ("insert", "replace"):
            for k in range(j1 + (i2 - i1 if tag == "replace" else 0), j2):
                h = mir.headings[k]
                out.append(
                    Finding(
                        code="heading-extra",
                        severity="error",
                        message=(
                            f"mirror has an extra level-{h.level} heading: "
                            f"{_q(h.text)} (mirror L{h.line})"
                        ),
                        mirror_line=h.line,
                    )
                )
        if tag == "replace":
            for k in range(min(i2 - i1, j2 - j1)):
                hs, hm = src.headings[i1 + k], mir.headings[j1 + k]
                out.append(
                    Finding(
                        code="heading-level",
                        severity="error",
                        message=(
                            f"heading level changed: source has H{hs.level} "
                            f"{_q(hs.text)} (L{hs.line}), mirror has H{hm.level} "
                            f"{_q(hm.text)} (L{hm.line})"
                        ),
                        source_line=hs.line,
                        mirror_line=hm.line,
                    )
                )


# -- code blocks ---------------------------------------------------------------


def _first_diff_line(a: str, b: str) -> int:
    """1-based index of the first differing line between two block bodies."""
    al, bl = a.split("\n"), b.split("\n")
    for i, (x, y) in enumerate(zip(al, bl)):
        if x != y:
            return i + 1
    return min(len(al), len(bl)) + 1


def _compare_code(src: Document, mir: Document, opts: CompareOptions, out: List[Finding]) -> None:
    if len(src.code_blocks) != len(mir.code_blocks):
        out.append(
            Finding(
                code="codeblock-count",
                severity="error",
                message=(
                    f"source has {len(src.code_blocks)} fenced code blocks, "
                    f"mirror has {len(mir.code_blocks)}"
                ),
            )
        )
    for idx, (cs, cm) in enumerate(zip(src.code_blocks, mir.code_blocks), start=1):
        if cs.lang != cm.lang:
            out.append(
                Finding(
                    code="codeblock-lang",
                    severity="error",
                    message=(
                        f"code block #{idx} language differs: source "
                        f"{cs.lang or '(none)'} (L{cs.line}), mirror "
                        f"{cm.lang or '(none)'} (L{cm.line})"
                    ),
                    source_line=cs.line,
                    mirror_line=cm.line,
                )
            )
        if opts.compare_code_content and cs.content != cm.content:
            out.append(
                Finding(
                    code="codeblock-drift",
                    severity="error",
                    message=(
                        f"code block #{idx} content differs from source "
                        f"(first difference at block line "
                        f"{_first_diff_line(cs.content, cm.content)}; "
                        f"source L{cs.line}, mirror L{cm.line})"
                    ),
                    source_line=cs.line,
                    mirror_line=cm.line,
                )
            )


# -- tables --------------------------------------------------------------------


def _compare_tables(src: Document, mir: Document, out: List[Finding]) -> None:
    if len(src.tables) != len(mir.tables):
        out.append(
            Finding(
                code="table-count",
                severity="error",
                message=(
                    f"source has {len(src.tables)} tables, mirror has {len(mir.tables)}"
                ),
            )
        )
    for idx, (ts, tm) in enumerate(zip(src.tables, mir.tables), start=1):
        if ts.columns != tm.columns:
            out.append(
                Finding(
                    code="table-shape",
                    severity="error",
                    message=(
                        f"table #{idx} has {ts.columns} columns in source (L{ts.line}) "
                        f"but {tm.columns} in mirror (L{tm.line})"
                    ),
                    source_line=ts.line,
                    mirror_line=tm.line,
                )
            )
        elif ts.rows != tm.rows:
            out.append(
                Finding(
                    code="table-rows",
                    severity="warning",
                    message=(
                        f"table #{idx} has {ts.rows} body rows in source (L{ts.line}) "
                        f"but {tm.rows} in mirror (L{tm.line})"
                    ),
                    source_line=ts.line,
                    mirror_line=tm.line,
                )
            )


# -- links and images ------------------------------------------------------------


def _strip_anchor(url: str) -> str:
    return url.split("#", 1)[0]


_LANG_SUFFIX_TMPL = r"\.%s\.(md|markdown)$"


def delocalize_url(url: str, lang: str) -> str:
    """Rewrite a mirror-local URL to its canonical form.

    ``guide.zh.md`` → ``guide.md`` and ``docs/zh/guide.md`` → ``docs/guide.md``
    so mirrors may point at sibling translations without tripping the gate.
    """
    if not lang or re.match(r"^[a-z]+://", url):
        return url
    out = re.sub(_LANG_SUFFIX_TMPL % re.escape(lang), r".\1", url, flags=re.IGNORECASE)
    parts = out.split("/")
    kept = [p for p in parts if p.casefold() != lang.casefold()]
    if len(kept) != len(parts) and kept:
        out = "/".join(kept)
        out = posixpath.normpath(out) if out else out
    return out


def _link_urls(doc: Document, opts: CompareOptions) -> Counter:
    urls: Counter = Counter()
    for link in doc.links:
        url = link.url
        if not opts.check_anchors:
            if url.startswith("#"):
                continue  # in-page anchors are language-specific slugs
            url = _strip_anchor(url)
        if not url:
            continue
        if any(fnmatch.fnmatch(url, pat) for pat in opts.ignore_links):
            continue
        urls[url] += 1
    return urls


def _compare_links(src: Document, mir: Document, opts: CompareOptions, out: List[Finding]) -> None:
    src_urls = _link_urls(src, opts)
    mir_urls = _link_urls(mir, opts)
    missing = src_urls - mir_urls
    extra = mir_urls - src_urls
    # Localized-link equivalence: an extra `x.zh.md` cancels a missing `x.md`.
    if opts.lang:
        for url in list(extra):
            canon = delocalize_url(url, opts.lang)
            while extra[url] and missing.get(canon, 0):
                extra[url] -= 1
                missing[canon] -= 1
        missing = +missing
        extra = +extra
    for url in sorted(missing):
        out.append(
            Finding(
                code="link-missing",
                severity="error",
                message=f"mirror is missing {missing[url]} link(s) to {url}",
            )
        )
    for url in sorted(extra):
        out.append(
            Finding(
                code="link-extra",
                severity="warning",
                message=f"mirror has {extra[url]} extra link(s) to {url}",
            )
        )


def _compare_images(src: Document, mir: Document, opts: CompareOptions, out: List[Finding]) -> None:
    a = [im.src for im in src.images]
    b = [delocalize_url(im.src, opts.lang) for im in mir.images]
    sm = SequenceMatcher(None, a, b, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        for k in range(i1, i2):
            im = src.images[k]
            out.append(
                Finding(
                    code="image-missing",
                    severity="error",
                    message=f"mirror is missing image {im.src} (source L{im.line})",
                    source_line=im.line,
                )
            )
        for k in range(j1, j2):
            im = mir.images[k]
            out.append(
                Finding(
                    code="image-extra",
                    severity="error",
                    message=f"mirror has unexpected image {im.src} (mirror L{im.line})",
                    mirror_line=im.line,
                )
            )


def _compare_lists(src: Document, mir: Document, out: List[Finding]) -> None:
    ns, nm = len(src.list_items), len(mir.list_items)
    if ns != nm:
        out.append(
            Finding(
                code="list-items",
                severity="warning",
                message=f"source has {ns} list items, mirror has {nm}",
            )
        )


def compare(src: Document, mir: Document, opts: Optional[CompareOptions] = None) -> List[Finding]:
    """Compare two parsed documents; an empty result means structural parity."""
    opts = opts or CompareOptions()
    out: List[Finding] = []
    _compare_headings(src, mir, out)
    _compare_code(src, mir, opts, out)
    _compare_tables(src, mir, out)
    _compare_links(src, mir, opts, out)
    _compare_images(src, mir, opts, out)
    _compare_lists(src, mir, out)
    return out


def worst_severity(findings: Sequence[Finding]) -> Optional[str]:
    """The most severe level present, or ``None`` for an empty list."""
    for level in SEVERITIES:
        if any(f.severity == level for f in findings):
            return level
    return None
