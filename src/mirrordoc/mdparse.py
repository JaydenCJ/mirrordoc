"""Structural Markdown parser.

mirrordoc never renders Markdown; it extracts the *skeleton* a translation
must preserve: headings, fenced code blocks, tables, links, images, list
items, and HTML comments. The parser is line-based and CommonMark-informed,
and it is deliberately **symmetric**: the canonical file and its mirror are
parsed by exactly the same rules, so the documented simplifications (no
indented code blocks, no raw-HTML block tracking — see
``docs/structure-model.md``) cancel out when the two skeletons are compared.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

ATX_RE = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?[ \t]*$")
FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})[ \t]*(.*)$")
SETEXT_RE = re.compile(r"^ {0,3}(=+|-+)[ \t]*$")
THEMATIC_RE = re.compile(
    r"^ {0,3}(?:(?:\*[ \t]*){3,}|(?:-[ \t]*){3,}|(?:_[ \t]*){3,})$"
)
LIST_RE = re.compile(r"^[ \t]{0,8}(?:([-+*])|(\d{1,9})[.)])[ \t]+\S")
REF_DEF_RE = re.compile(r"^ {0,3}\[([^\]]+)\]:[ \t]*(?:<([^<>]*)>|(\S+))")
AUTOLINK_RE = re.compile(r"<([A-Za-z][A-Za-z0-9+.\-]*:[^<>\s]+)>")
QUOTE_RE = re.compile(r"^ {0,3}> ?")
DELIM_CELL_RE = re.compile(r":?-+:?")


@dataclass(frozen=True)
class Heading:
    """One ATX or setext heading."""

    level: int
    text: str
    line: int


@dataclass(frozen=True)
class CodeBlock:
    """One fenced code block (``` or ~~~)."""

    lang: str
    content: str
    line: int


@dataclass(frozen=True)
class Table:
    """One GFM pipe table: shape only, cells are prose and may be translated."""

    columns: int
    rows: int  # body rows, excluding header and delimiter
    line: int


@dataclass(frozen=True)
class Link:
    """One link with a resolved destination.

    ``kind`` is ``inline``, ``reference``, ``autolink``, or ``definition``.
    """

    url: str
    text: str
    line: int
    kind: str


@dataclass(frozen=True)
class Image:
    """One inline image."""

    src: str
    alt: str
    line: int


@dataclass(frozen=True)
class ListItem:
    """One list item start; ``marker`` is ``bullet`` or ``ordered``."""

    marker: str
    line: int


@dataclass(frozen=True)
class Comment:
    """One HTML comment (``<!-- ... -->``), possibly spanning lines."""

    text: str
    line: int


@dataclass
class Document:
    """The structural skeleton of one Markdown file."""

    headings: List[Heading] = field(default_factory=list)
    code_blocks: List[CodeBlock] = field(default_factory=list)
    tables: List[Table] = field(default_factory=list)
    links: List[Link] = field(default_factory=list)
    images: List[Image] = field(default_factory=list)
    list_items: List[ListItem] = field(default_factory=list)
    comments: List[Comment] = field(default_factory=list)
    line_count: int = 0


def _escaped(s: str, i: int) -> bool:
    """True when the character at ``s[i]`` is backslash-escaped."""
    n = 0
    j = i - 1
    while j >= 0 and s[j] == "\\":
        n += 1
        j -= 1
    return n % 2 == 1


def _mask_code_spans(s: str) -> str:
    """Replace inline code spans with spaces so ``[x](y)`` inside them is inert."""
    out = list(s)
    i = 0
    while i < len(s):
        if s[i] != "`" or _escaped(s, i):
            i += 1
            continue
        j = i
        while j < len(s) and s[j] == "`":
            j += 1
        n = j - i
        # Find a closing run of exactly n backticks.
        k = j
        close = -1
        while k < len(s):
            if s[k] == "`":
                m = k
                while m < len(s) and s[m] == "`":
                    m += 1
                if m - k == n:
                    close = m
                    break
                k = m
            else:
                k += 1
        if close == -1:
            i = j
            continue
        for p in range(i, close):
            out[p] = " "
        i = close
    return "".join(out)


def _match_delims(s: str, start: int, open_ch: str, close_ch: str) -> Optional[int]:
    """Index of the delimiter closing ``s[start]``, honoring nesting and escapes."""
    depth = 0
    i = start
    while i < len(s):
        c = s[i]
        if c == "\\":
            i += 2
            continue
        if c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return None


def _extract_dest(inner: str) -> str:
    """Destination from the ``(...)`` part of an inline link (title dropped)."""
    inner = inner.strip()
    if inner.startswith("<"):
        end = inner.find(">")
        return inner[1:end] if end != -1 else inner[1:]
    return inner.split(None, 1)[0] if inner else ""


def _split_cells(s: str) -> List[str]:
    """Split one table row into cells on unescaped pipes, trimming edge pipes."""
    cells: List[str] = []
    buf: List[str] = []
    i = 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            buf.append(s[i : i + 2])
            i += 2
            continue
        if c == "|":
            cells.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(c)
        i += 1
    cells.append("".join(buf))
    stripped = s.strip()
    if cells and stripped.startswith("|") and cells[0].strip() == "":
        cells = cells[1:]
    if (
        cells
        and stripped.endswith("|")
        and not stripped.endswith("\\|")
        and cells[-1].strip() == ""
    ):
        cells = cells[:-1]
    return cells


def _is_table_delimiter(line: str) -> bool:
    """True for a GFM delimiter row like ``| --- | :--: |`` (pipe required)."""
    s = line.strip()
    if "|" not in s or not re.fullmatch(r"\|?[ \t:\-|]+\|?", s):
        return False
    cells = _split_cells(s)
    if not cells:
        return False
    return all(DELIM_CELL_RE.fullmatch(c.strip()) for c in cells)


def _contains_unescaped_pipe(s: str) -> bool:
    return any(c == "|" and not _escaped(s, i) for i, c in enumerate(s))


class _Parser:
    """Single-pass line parser; one instance per :func:`parse` call."""

    def __init__(self) -> None:
        self.doc = Document()
        self.ref_defs: Dict[str, str] = {}
        # (text, label, line, is_image) awaiting resolution against ref_defs
        self.pending_refs: List[Tuple[str, str, int, bool]] = []
        self.in_comment = False
        self.comment_buf: List[str] = []
        self.comment_line = 0
        self.para_open = False  # a paragraph line directly above (for setext)

    # -- comments -----------------------------------------------------------

    def _strip_comments(self, line: str, line_no: int) -> str:
        """Extract HTML comments, blanking them out of the visible line."""
        visible: List[str] = []
        rest = line
        while True:
            if self.in_comment:
                end = rest.find("-->")
                if end == -1:
                    self.comment_buf.append(rest)
                    return "".join(visible)
                self.comment_buf.append(rest[:end])
                self.doc.comments.append(
                    Comment(text="\n".join(self.comment_buf).strip(), line=self.comment_line)
                )
                self.in_comment = False
                self.comment_buf = []
                rest = rest[end + 3 :]
                continue
            start = rest.find("<!--")
            if start == -1:
                visible.append(rest)
                return "".join(visible)
            visible.append(rest[:start])
            self.in_comment = True
            self.comment_line = line_no
            rest = rest[start + 4 :]

    # -- inline elements ----------------------------------------------------

    def _scan_inline(self, raw: str, line_no: int) -> None:
        s = _mask_code_spans(raw)
        i = 0
        while i < len(s):
            c = s[i]
            if c == "<" and not _escaped(s, i):
                m = AUTOLINK_RE.match(s, i)
                if m:
                    self.doc.links.append(
                        Link(url=m.group(1), text=m.group(1), line=line_no, kind="autolink")
                    )
                    i = m.end()
                    continue
            if c == "[" and not _escaped(s, i):
                is_image = i > 0 and s[i - 1] == "!" and not _escaped(s, i - 1)
                end = _match_delims(s, i, "[", "]")
                if end is None:
                    i += 1
                    continue
                text = s[i + 1 : end].strip()
                after = end + 1
                if after < len(s) and s[after] == "(":
                    close = _match_delims(s, after, "(", ")")
                    if close is not None:
                        dest = _extract_dest(s[after + 1 : close])
                        if is_image:
                            self.doc.images.append(Image(src=dest, alt=text, line=line_no))
                        else:
                            self.doc.links.append(
                                Link(url=dest, text=text, line=line_no, kind="inline")
                            )
                        i = close + 1
                        continue
                if after < len(s) and s[after] == "[":
                    label_end = s.find("]", after)
                    if label_end != -1:
                        label = s[after + 1 : label_end].strip() or text
                        self.pending_refs.append((text, label, line_no, is_image))
                        i = label_end + 1
                        continue
                # Shortcut reference: [text] — a link only if a definition exists.
                self.pending_refs.append((text, text, line_no, is_image))
                i = end + 1
                continue
            i += 1

    def _resolve_refs(self) -> None:
        by_line: List[Tuple[int, str, str, bool]] = []
        for text, label, line_no, is_image in self.pending_refs:
            url = self.ref_defs.get(_norm_label(label))
            if url is not None:
                by_line.append((line_no, text, url, is_image))
        for line_no, text, url, is_image in by_line:
            if is_image:
                self.doc.images.append(Image(src=url, alt=text, line=line_no))
            else:
                self.doc.links.append(Link(url=url, text=text, line=line_no, kind="reference"))
        self.doc.links.sort(key=lambda l: l.line)
        self.doc.images.sort(key=lambda im: im.line)

    # -- main loop ----------------------------------------------------------

    def parse(self, text: str) -> Document:
        lines = text.splitlines()
        self.doc.line_count = len(lines)
        fence: Optional[Tuple[str, int, str, int, int]] = None
        # fence = (char, min_len, lang, start_line, quote_depth)
        fence_body: List[str] = []
        i = 0
        n = len(lines)
        while i < n:
            raw = lines[i]
            line_no = i + 1

            if fence is not None:
                char, min_len, lang, start_line, qdepth = fence
                body_line = raw
                for _ in range(qdepth):
                    m = QUOTE_RE.match(body_line)
                    if not m:
                        break
                    body_line = body_line[m.end() :]
                fm = FENCE_RE.match(body_line)
                if fm and fm.group(1)[0] == char and len(fm.group(1)) >= min_len and not fm.group(2).strip():
                    self.doc.code_blocks.append(
                        CodeBlock(lang=lang, content="\n".join(fence_body), line=start_line)
                    )
                    fence = None
                    fence_body = []
                else:
                    fence_body.append(body_line)
                i += 1
                continue

            # Blockquote markers are stripped so quoted structure still counts.
            qdepth = 0
            line = raw
            while True:
                m = QUOTE_RE.match(line)
                if not m:
                    break
                line = line[m.end() :]
                qdepth += 1

            line = self._strip_comments(line, line_no)

            if not line.strip():
                self.para_open = False
                i += 1
                continue

            fm = FENCE_RE.match(line)
            if fm:
                info = fm.group(2).strip()
                # An info string containing a backtick cannot open a ` fence.
                if not (fm.group(1)[0] == "`" and "`" in info):
                    lang = info.split()[0].lower() if info else ""
                    fence = (fm.group(1)[0], len(fm.group(1)), lang, line_no, qdepth)
                    fence_body = []
                    self.para_open = False
                    i += 1
                    continue

            am = ATX_RE.match(line)
            if am:
                text_part = (am.group(2) or "").strip()
                text_part = re.sub(r"[ \t]+#+$", "", text_part).strip()
                self.doc.headings.append(
                    Heading(level=len(am.group(1)), text=text_part, line=line_no)
                )
                self.para_open = False
                i += 1
                continue

            sm = SETEXT_RE.match(line)
            if sm and self.para_open:
                prev = lines[i - 1]
                while True:
                    m = QUOTE_RE.match(prev)
                    if not m:
                        break
                    prev = prev[m.end() :]
                level = 1 if sm.group(1)[0] == "=" else 2
                self.doc.headings.append(
                    Heading(level=level, text=prev.strip(), line=i)
                )
                self.para_open = False
                i += 1
                continue

            if THEMATIC_RE.match(line):
                self.para_open = False
                i += 1
                continue

            rm = REF_DEF_RE.match(line)
            if rm:
                url = rm.group(2) if rm.group(2) is not None else rm.group(3)
                self.doc.links.append(
                    Link(url=url, text=rm.group(1).strip(), line=line_no, kind="definition")
                )
                self.ref_defs.setdefault(_norm_label(rm.group(1)), url)
                self.para_open = False
                i += 1
                continue

            # GFM table: header row + delimiter row lookahead.
            if _contains_unescaped_pipe(_mask_code_spans(line)) and i + 1 < n:
                nxt = lines[i + 1]
                for _ in range(qdepth):
                    m = QUOTE_RE.match(nxt)
                    if not m:
                        break
                    nxt = nxt[m.end() :]
                if _is_table_delimiter(nxt):
                    header_cells = _split_cells(_mask_code_spans(line).strip())
                    delim_cells = _split_cells(nxt.strip())
                    if len(header_cells) == len(delim_cells):
                        self._scan_inline(line, line_no)
                        rows = 0
                        j = i + 2
                        while j < n:
                            row = lines[j]
                            for _ in range(qdepth):
                                m = QUOTE_RE.match(row)
                                if not m:
                                    break
                                row = row[m.end() :]
                            if not row.strip() or not _contains_unescaped_pipe(
                                _mask_code_spans(row)
                            ):
                                break
                            self._scan_inline(row, j + 1)
                            rows += 1
                            j += 1
                        self.doc.tables.append(
                            Table(columns=len(header_cells), rows=rows, line=line_no)
                        )
                        self.para_open = False
                        i = j
                        continue

            lm = LIST_RE.match(line)
            if lm:
                marker = "bullet" if lm.group(1) else "ordered"
                self.doc.list_items.append(ListItem(marker=marker, line=line_no))

            self._scan_inline(line, line_no)
            self.para_open = lm is None
            i += 1

        if fence is not None:
            # Unterminated fence: still record it so both sides agree.
            char, min_len, lang, start_line, _q = fence
            self.doc.code_blocks.append(
                CodeBlock(lang=lang, content="\n".join(fence_body), line=start_line)
            )
        self._resolve_refs()
        return self.doc


def _norm_label(label: str) -> str:
    return " ".join(label.split()).casefold()


def parse(text: str) -> Document:
    """Parse Markdown ``text`` into its structural :class:`Document` skeleton."""
    return _Parser().parse(text.replace("\r\n", "\n").replace("\r", "\n"))
