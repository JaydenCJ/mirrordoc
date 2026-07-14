#!/usr/bin/env bash
# Smoke test for mirrordoc: drive the real CLI end to end — pair discovery,
# the structure gate on the shipped example docs, JSON output, the repo's
# own trilingual README self-check, and the stamp -> stale -> re-stamp cycle
# in a throwaway git repository. Self-contained: pure stdlib, no network.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-python3}"
if [ -x "$ROOT/.venv/bin/python" ]; then
  PYTHON="$ROOT/.venv/bin/python"
fi

# Zero runtime dependencies, so running from src/ needs no install.
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/mirrordoc-smoke.XXXXXX")"
trap 'rm -rf "$WORKDIR"' EXIT

fail() { echo "SMOKE FAIL: $1" >&2; exit 1; }

echo "[smoke] python: $("$PYTHON" --version 2>&1)"

# 1. Pair discovery on the shipped example: suffix + directory conventions.
pairs_out="$("$PYTHON" -m mirrordoc pairs "$ROOT/examples/demo-docs")"
echo "$pairs_out" | sed 's/^/[pairs] /'
echo "$pairs_out" | grep -q "README.zh.md" || fail "pairs missed the zh suffix mirror"
echo "$pairs_out" | grep -q "docs/ja/guide.md" || fail "pairs missed the directory-style mirror"

# 2. Structure gate: ja is faithful, zh is deliberately drifted -> exit 1.
set +e
check_out="$("$PYTHON" -m mirrordoc check "$ROOT/examples/demo-docs" --no-stale)"
check_rc=$?
set -e
echo "$check_out" | sed 's/^/[check] /'
[ "$check_rc" -eq 1 ] || fail "check on drifted example should exit 1, got $check_rc"
echo "$check_out" | grep -q "heading-missing" || fail "missing-heading drift not reported"
echo "$check_out" | grep -q "codeblock-drift" || fail "translated code block not reported"
echo "$check_out" | grep -A1 "README.ja.md" | grep -q "in sync" \
  || fail "faithful ja mirror should be in sync"

# 3. JSON output is valid and schema-versioned (check exits 1 on the drift).
set +e
json_out="$("$PYTHON" -m mirrordoc check "$ROOT/examples/demo-docs" --no-stale --format json)"
set -e
echo "$json_out" \
  | "$PYTHON" -c 'import json,sys; d=json.load(sys.stdin); assert d["schema_version"]==1; assert d["summary"]["errors"]>=1' \
  || fail "JSON report invalid"

# 4. Self-check: this repository's trilingual README must pass its own gate.
self_out="$("$PYTHON" -m mirrordoc check "$ROOT" --no-stale)" \
  || fail "the repository's own READMEs are out of sync"
echo "$self_out" | sed 's/^/[self] /'
echo "$self_out" | grep -q "README.zh.md" || fail "self-check did not cover README.zh.md"

# 5. Stamp + staleness cycle in a throwaway git repository.
if git --version >/dev/null 2>&1; then
  REPO="$WORKDIR/repo"
  mkdir -p "$REPO"
  export GIT_AUTHOR_NAME=smoke GIT_AUTHOR_EMAIL=smoke@example.test
  export GIT_COMMITTER_NAME=smoke GIT_COMMITTER_EMAIL=smoke@example.test
  export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null
  git -C "$REPO" init -q -b main
  cp "$ROOT/examples/demo-docs/README.md" "$REPO/README.md"
  cp "$ROOT/examples/demo-docs/README.ja.md" "$REPO/README.ja.md"
  git -C "$REPO" add . && git -C "$REPO" commit -qm "docs"
  "$PYTHON" -m mirrordoc stamp "$REPO/README.ja.md" | sed 's/^/[stamp] /'
  git -C "$REPO" add . && git -C "$REPO" commit -qm "stamp"
  "$PYTHON" -m mirrordoc check "$REPO" >/dev/null \
    || fail "freshly stamped mirror should pass"
  printf '\nExtra canonical paragraph.\n' >> "$REPO/README.md"
  git -C "$REPO" add . && git -C "$REPO" commit -qm "update source"
  set +e
  stale_out="$("$PYTHON" -m mirrordoc check "$REPO")"
  stale_rc=$?
  set -e
  echo "$stale_out" | sed 's/^/[stale] /'
  [ "$stale_rc" -eq 1 ] || fail "stale mirror should exit 1, got $stale_rc"
  echo "$stale_out" | grep -q "stale-marker" || fail "stale-marker not reported"
  "$PYTHON" -m mirrordoc stamp "$REPO/README.ja.md" | sed 's/^/[stamp] /'
  git -C "$REPO" add . && git -C "$REPO" commit -qm "re-stamp"
  "$PYTHON" -m mirrordoc check "$REPO" >/dev/null \
    || fail "re-stamped mirror should pass again"
else
  echo "[smoke] git not found; skipping staleness cycle"
fi

# 6. --version agrees with the package metadata.
version_out="$("$PYTHON" -m mirrordoc --version)"
pkg_version="$("$PYTHON" -c 'import mirrordoc; print(mirrordoc.__version__)')"
[ "$version_out" = "mirrordoc $pkg_version" ] \
  || fail "--version mismatch: '$version_out' vs package '$pkg_version'"

echo "SMOKE OK"
