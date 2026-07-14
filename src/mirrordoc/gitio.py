"""Thin wrappers around the local ``git`` binary.

Staleness checks are the only part of mirrordoc that touches git, and they
degrade gracefully: outside a repository (or without git installed) every
helper returns ``None`` and structure checking still works. No command here
ever contacts a remote.
"""

from __future__ import annotations

import subprocess
from typing import List, Optional, Tuple

from .errors import GitError


def run_git(args: List[str], cwd: str) -> str:
    """Run ``git <args>`` in ``cwd``; return stdout or raise :class:`GitError`."""
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
    except (FileNotFoundError, OSError) as exc:
        raise GitError(f"git is not available: {exc}") from exc
    if proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def repo_root(path: str) -> Optional[str]:
    """Top-level directory of the repository containing ``path``, or ``None``."""
    try:
        out = run_git(["rev-parse", "--show-toplevel"], cwd=path)
    except GitError:
        return None
    return out.strip() or None


def last_commit(root: str, relpath: str) -> Optional[Tuple[str, int]]:
    """``(sha, committer_timestamp)`` of the last commit touching ``relpath``.

    ``None`` when the file has never been committed (untracked or new).
    """
    try:
        out = run_git(
            ["log", "-1", "--format=%H %ct", "--", relpath], cwd=root
        ).strip()
    except GitError:
        return None
    if not out:
        return None
    sha, ts = out.split()
    return sha, int(ts)


def commits_since(root: str, sha: str, relpath: str) -> Optional[int]:
    """How many commits touched ``relpath`` after ``sha``; ``None`` if unknown.

    A stamped commit that no longer resolves (rebased away, shallow clone)
    yields ``None`` so callers can fall back to timestamp comparison.
    """
    try:
        run_git(["rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}"], cwd=root)
    except GitError:
        return None
    out = run_git(["rev-list", "--count", f"{sha}..HEAD", "--", relpath], cwd=root)
    return int(out.strip())
