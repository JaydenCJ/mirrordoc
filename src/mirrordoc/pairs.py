"""Mirror-pair discovery.

Two filesystem conventions are recognized out of the box, plus explicit pairs
from configuration:

- **suffix**:    ``README.zh.md``      mirrors ``README.md``
- **directory**: ``docs/ja/guide.md``  mirrors ``docs/guide.md``

A candidate language tag only counts when its base is a real ISO 639-1 code,
so ``README.old.md`` or ``notes.v2.md`` are never mistaken for mirrors.
"""

from __future__ import annotations

import fnmatch
import os
import posixpath
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .errors import ConfigError

# The full ISO 639-1 two-letter code set.
ISO_639_1 = frozenset(
    """
    aa ab ae af ak am an ar as av ay az ba be bg bh bi bm bn bo br bs ca ce ch
    co cr cs cu cv cy da de dv dz ee el en eo es et eu fa ff fi fj fo fr fy ga
    gd gl gn gu gv ha he hi ho hr ht hu hy hz ia id ie ig ii ik io is it iu ja
    jv ka kg ki kj kk kl km kn ko kr ks ku kv kw ky la lb lg li ln lo lt lu lv
    mg mh mi mk ml mn mr ms mt my na nb nd ne ng nl nn no nr nv ny oc oj om or
    os pa pi pl ps pt qu rm rn ro ru rw sa sc sd se sg si sk sl sm sn so sq sr
    ss st su sv sw ta te tg th ti tk tl tn to tr ts tt tw ty ug uk ur uz ve vi
    vo wa wo xh yi yo za zh zu
    """.split()
)

# `zh`, `zh-CN`, `pt_BR`, `zh-Hans`, `es-419` are all accepted.
_LANG_TAG_RE = re.compile(r"^([A-Za-z]{2})(?:[-_]([A-Za-z]{2}|[A-Za-z]{4}|\d{3}))?$")

MARKDOWN_EXTS = (".md", ".markdown")

DEFAULT_EXCLUDE_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".tox",
        ".venv",
        ".mypy_cache",
        ".pytest_cache",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "target",
        "venv",
    }
)


@dataclass(frozen=True)
class Pair:
    """A canonical file and one translated mirror (root-relative posix paths)."""

    source: str
    mirror: str
    lang: str


def is_lang_tag(tag: str) -> bool:
    """True for a plausible BCP-47-ish tag whose base is ISO 639-1."""
    m = _LANG_TAG_RE.match(tag)
    return bool(m) and m.group(1).lower() in ISO_639_1


def lang_base(tag: str) -> str:
    """The lowercase primary subtag: ``zh-CN`` → ``zh``."""
    return re.split(r"[-_]", tag, maxsplit=1)[0].lower()


def split_lang_suffix(filename: str) -> Optional[Tuple[str, str, str]]:
    """``README.zh-CN.md`` → ``("README", "zh-CN", ".md")``; else ``None``."""
    root, ext = posixpath.splitext(filename)
    if ext.lower() not in MARKDOWN_EXTS:
        return None
    stem, dot, tag = root.rpartition(".")
    if not dot or not stem or not is_lang_tag(tag):
        return None
    return stem, tag, ext


def _excluded(rel: str, patterns: Sequence[str]) -> bool:
    return any(fnmatch.fnmatch(rel, pat) for pat in patterns)


def _walk_markdown(root: str, exclude: Sequence[str]) -> List[str]:
    """All root-relative posix paths of Markdown files, deterministically sorted."""
    found: List[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root)
        rel_dir = "" if rel_dir == "." else rel_dir.replace(os.sep, "/")
        dirnames[:] = sorted(
            d
            for d in dirnames
            if d not in DEFAULT_EXCLUDE_DIRS
            and not _excluded(posixpath.join(rel_dir, d) if rel_dir else d, exclude)
        )
        for name in sorted(filenames):
            if not name.lower().endswith(MARKDOWN_EXTS):
                continue
            rel = posixpath.join(rel_dir, name) if rel_dir else name
            if not _excluded(rel, exclude):
                found.append(rel)
    return found


def _suffix_pairs(files: Set[str]) -> List[Pair]:
    pairs: List[Pair] = []
    for rel in sorted(files):
        dirname, name = posixpath.split(rel)
        parts = split_lang_suffix(name)
        if parts is None:
            continue
        stem, tag, ext = parts
        source = posixpath.join(dirname, stem + ext) if dirname else stem + ext
        if source in files:
            pairs.append(Pair(source=source, mirror=rel, lang=tag))
    return pairs


def _directory_pairs(files: Set[str]) -> List[Pair]:
    pairs: List[Pair] = []
    for rel in sorted(files):
        segments = rel.split("/")
        for idx, seg in enumerate(segments[:-1]):
            if not is_lang_tag(seg):
                continue
            candidate = "/".join(segments[:idx] + segments[idx + 1 :])
            if candidate in files and candidate != rel:
                pairs.append(Pair(source=candidate, mirror=rel, lang=seg))
    return pairs


def _explicit_pairs(
    root: str, raw_pairs: Iterable[Dict[str, str]], files: Set[str]
) -> List[Pair]:
    pairs: List[Pair] = []
    for entry in raw_pairs:
        source, mirror = entry["source"], entry["mirror"]
        for rel in (source, mirror):
            if not os.path.isfile(os.path.join(root, rel)):
                raise ConfigError(f"configured pair references a missing file: {rel}")
        lang = entry.get("lang", "")
        if not lang:
            parts = split_lang_suffix(posixpath.basename(mirror))
            lang = parts[1] if parts else "und"
        files.add(source)
        files.add(mirror)
        pairs.append(Pair(source=source, mirror=mirror, lang=lang))
    return pairs


def discover(
    root: str,
    langs: Sequence[str] = (),
    exclude: Sequence[str] = (),
    explicit: Iterable[Dict[str, str]] = (),
) -> List[Pair]:
    """Find all (canonical, mirror) pairs under ``root``.

    ``langs`` restricts results to the given primary subtags (``zh`` matches
    ``zh-CN``); ``exclude`` holds fnmatch globs against root-relative paths;
    ``explicit`` adds configured pairs that conventions cannot express.
    """
    files = set(_walk_markdown(root, exclude))
    seen: Set[Tuple[str, str]] = set()
    pairs: List[Pair] = []
    for pair in _explicit_pairs(root, explicit, files) + _suffix_pairs(files) + _directory_pairs(files):
        key = (pair.source, pair.mirror)
        if key in seen:
            continue
        seen.add(key)
        pairs.append(pair)
    # A file that is itself a mirror can never be a canonical source.
    mirrors = {p.mirror for p in pairs}
    pairs = [p for p in pairs if p.source not in mirrors]
    if langs:
        wanted = {lang_base(tag) for tag in langs}
        pairs = [p for p in pairs if lang_base(p.lang) in wanted]
    return sorted(pairs, key=lambda p: (p.source, p.lang, p.mirror))
