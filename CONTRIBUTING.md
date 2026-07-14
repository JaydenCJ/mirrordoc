# Contributing to mirrordoc

Thanks for your interest in contributing. Issues, discussions, and pull
requests are all welcome.

## Getting started

You need Python ≥ 3.9 and git (used only by the staleness checks, `mirrordoc
stamp`, and the end-to-end tests; structure comparison runs anywhere).

```bash
git clone https://github.com/JaydenCJ/mirrordoc
cd mirrordoc
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                 # 90 tests, fully offline
bash scripts/smoke.sh  # end-to-end CLI check, must print SMOKE OK
```

`scripts/smoke.sh` drives the real CLI: pair discovery and the structure gate
on the shipped example docs, the repository's own trilingual-README
self-check, and the stamp → stale → re-stamp cycle in a throwaway git
repository. It must print `SMOKE OK` before a pull request is reviewed.

## Before you open a pull request

1. `python3 -m mirrordoc check .` — this repository gates its own three
   READMEs; keep them structurally identical.
2. `pytest` — must pass, deterministically and offline.
3. `bash scripts/smoke.sh` — must print `SMOKE OK`.
4. Add tests for behavior changes; keep logic in pure, unit-testable modules
   (`mdparse`, `structdiff`, `pairs`, `staleness` take no CLI state).
5. Keep the three READMEs aligned: `README.md`, `README.zh.md`, and
   `README.ja.md` are line-for-line translations — update all three
   (English is authoritative).

## Ground rules

- **No runtime dependencies.** The package is standard-library only; that is
  a feature. Test-only dependencies belong in the `dev` extra.
- **No network calls, ever.** The only external process mirrordoc may spawn
  is local `git`. No telemetry, nothing phones home.
- **Parser changes need docs and tests.** Anything that alters what counts as
  structure must update `docs/structure-model.md` in the same pull request,
  and must stay symmetric between source and mirror.
- Code comments and docstrings are written in English.

## Reporting bugs

Please include `mirrordoc --version`, the exact command, `mirrordoc outline`
output for both files of the affected pair (paths may be redacted), and the
report — `--format json` is ideal because it carries codes and line numbers.

## Security

Please do not open public issues for suspected vulnerabilities; use GitHub's
private vulnerability reporting on the repository instead.
