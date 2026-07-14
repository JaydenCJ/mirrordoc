"""Staleness detection: has the canonical file changed since the mirror did?

Two mechanisms, strongest first:

1. **Sync marker** — the mirror carries a pinned comment written by
   ``mirrordoc stamp``::

       <!-- mirrordoc: source=README.md commit=4f2a9c1... -->

   If any commit has touched the source since that commit, the mirror is
   stale — an *error*, because the pin is explicit and exact.
2. **Commit-time fallback** — without a marker, the last commit dates of the
   two files are compared; a newer source is a *warning*, since commit order
   is only circumstantial evidence.

Everything runs against the local repository; there is no network.
"""

from __future__ import annotations

import datetime as _dt
import os
import posixpath
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from . import gitio
from .errors import UsageError
from .structdiff import Finding

MARKER_RE = re.compile(
    r"<!--\s*mirrordoc:\s*source=(?P<source>\S+)\s+commit=(?P<commit>[0-9a-fA-F]{7,40})\s*-->"
)


@dataclass(frozen=True)
class Marker:
    """A parsed sync marker: source path (relative to the mirror) + commit."""

    source: str
    commit: str
    line: int


def find_marker(text: str) -> Optional[Marker]:
    """The first sync marker in ``text``, or ``None``."""
    for i, line in enumerate(text.splitlines(), start=1):
        m = MARKER_RE.search(line)
        if m:
            return Marker(source=m.group("source"), commit=m.group("commit"), line=i)
    return None


def _iso(ts: int) -> str:
    return _dt.datetime.fromtimestamp(ts, _dt.timezone.utc).strftime("%Y-%m-%d")


def _norm_rel(base_dir: str, target: str) -> str:
    """Resolve ``target`` (posix, relative to ``base_dir``) to a repo-relative path."""
    joined = posixpath.join(base_dir, target) if base_dir else target
    return posixpath.normpath(joined)


def check_staleness(
    source_abs: str,
    mirror_abs: str,
    mirror_text: str,
    require_marker: bool = False,
) -> Tuple[List[Finding], Optional[str]]:
    """Staleness findings for one pair, plus a note when the check is skipped."""
    findings: List[Finding] = []
    root = gitio.repo_root(os.path.dirname(mirror_abs) or ".")
    if root is None:
        return findings, "staleness skipped: not inside a git repository"
    src_rel = os.path.relpath(source_abs, root).replace(os.sep, "/")
    mir_rel = os.path.relpath(mirror_abs, root).replace(os.sep, "/")
    src_ci = gitio.last_commit(root, src_rel)
    if src_ci is None:
        return findings, f"staleness skipped: {src_rel} has no commits yet"
    src_sha, src_ts = src_ci

    marker = find_marker(mirror_text)
    if marker is not None:
        expected = _norm_rel(posixpath.dirname(mir_rel), marker.source)
        if expected != src_rel:
            findings.append(
                Finding(
                    code="marker-source-mismatch",
                    severity="warning",
                    message=(
                        f"sync marker points at {marker.source} "
                        f"(resolves to {expected}), expected {src_rel}"
                    ),
                    mirror_line=marker.line,
                )
            )
        count = gitio.commits_since(root, marker.commit, src_rel)
        if count is None:
            findings.append(
                Finding(
                    code="marker-unknown-commit",
                    severity="warning",
                    message=(
                        f"stamped commit {marker.commit[:12]} does not resolve in "
                        f"this repository; falling back to commit dates"
                    ),
                    mirror_line=marker.line,
                )
            )
        elif count > 0:
            findings.append(
                Finding(
                    code="stale-marker",
                    severity="error",
                    message=(
                        f"{count} commit(s) touched {src_rel} since the mirror was "
                        f"stamped at {marker.commit[:12]} — re-translate and "
                        f"run `mirrordoc stamp`"
                    ),
                    mirror_line=marker.line,
                )
            )
        else:
            return findings, None  # pinned and up to date
        if count is not None:
            return findings, None
        # unknown commit: fall through to the timestamp heuristic

    elif require_marker:
        findings.append(
            Finding(
                code="marker-missing",
                severity="error",
                message=(
                    f"{mir_rel} has no sync marker; run "
                    f"`mirrordoc stamp {mir_rel}` after translating"
                ),
            )
        )

    mir_ci = gitio.last_commit(root, mir_rel)
    if mir_ci is None:
        return findings, f"staleness skipped: {mir_rel} has no commits yet"
    _mir_sha, mir_ts = mir_ci
    if src_ts > mir_ts:
        findings.append(
            Finding(
                code="stale-commit",
                severity="warning",
                message=(
                    f"{src_rel} was last touched {_iso(src_ts)}, after the mirror's "
                    f"last commit {_iso(mir_ts)} — the translation may be behind"
                ),
            )
        )
    return findings, None


def stamp(source_abs: str, mirror_abs: str) -> str:
    """Write or refresh the sync marker in the mirror; returns the pinned sha."""
    root = gitio.repo_root(os.path.dirname(mirror_abs) or ".")
    if root is None:
        raise UsageError("stamp requires the mirror to live inside a git repository")
    src_rel = os.path.relpath(source_abs, root).replace(os.sep, "/")
    src_ci = gitio.last_commit(root, src_rel)
    if src_ci is None:
        raise UsageError(
            f"cannot stamp: {src_rel} has no commits yet (commit the source first)"
        )
    sha, _ts = src_ci
    rel_source = posixpath.relpath(
        src_rel, posixpath.dirname(os.path.relpath(mirror_abs, root).replace(os.sep, "/"))
    )
    marker_line = f"<!-- mirrordoc: source={rel_source} commit={sha} -->"
    with open(mirror_abs, "r", encoding="utf-8") as fh:
        text = fh.read()
    if MARKER_RE.search(text):
        new_text = MARKER_RE.sub(marker_line, text, count=1)
    else:
        new_text = marker_line + "\n" + text
    with open(mirror_abs, "w", encoding="utf-8") as fh:
        fh.write(new_text)
    return sha
