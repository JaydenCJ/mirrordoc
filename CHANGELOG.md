# Changelog

All notable changes to this project are documented in this file. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-07-13

### Added

- Structural Markdown parser extracting the skeleton a translation must
  preserve: ATX + setext headings, backtick/tilde fences (including
  unterminated ones), GFM pipe tables with escaped-pipe cell splitting,
  inline/reference/autolink links, images, list items, and HTML comments;
  inline code spans hide link syntax and fences hide headings, symmetrically
  on both sides (`docs/structure-model.md`).
- Structure comparison engine with stable finding codes: heading skeleton
  (sequence-aligned missing/extra/level changes), byte-identical code blocks
  with first-differing-line reporting, table shape, link destination
  multisets, image sequences, and list-item counts. Anchor fragments are
  ignored by default (translated slugs differ) and localized links
  (`CHANGELOG.zh.md`, `docs/zh/guide.md`) satisfy their canonical
  counterparts without weakening exact matches.
- Mirror-pair discovery for the suffix (`README.zh.md`) and directory
  (`docs/ja/guide.md`) conventions, validated against the full ISO 639-1
  code set with optional region/script subtags so `README.old.md` is never
  mistaken for a translation; explicit pairs via config.
- Git staleness checks, local-only: a `mirrordoc stamp` sync marker pins the
  mirror to the source's commit (later source commits are an error), with a
  commit-date comparison fallback (warning); outside a repository the check
  degrades to a note and structure gating still works.
- `mirrordoc` CLI: `check` (discover + gate), `diff` (one explicit pair),
  `pairs`, `outline`, and `stamp`. Exit codes: 0 in sync, 1 drift or
  staleness, 2 usage/config error; `--strict` promotes warnings.
- Three deterministic report formats from one report object: aligned text,
  schema-versioned JSON with sorted keys, and a Markdown fragment ready to
  paste into a PR comment.
- Strict `.mirrordoc.json` configuration (langs, excludes, explicit pairs,
  ignored link globs, code/anchor/staleness toggles) — unknown keys are
  rejected loudly.
- Runnable example tree (`examples/demo-docs`) with one faithful and one
  deliberately drifted mirror, and the repository gating its own trilingual
  README via its own `.mirrordoc.json`.
- 90 pytest tests (parser, comparison, discovery, staleness against real
  local git repositories, renderers, config, CLI) and `scripts/smoke.sh`.

### Notes

- The repository ships no CI workflow; verification is local —
  `pip install -e '.[dev]' && pytest && bash scripts/smoke.sh`.

[0.1.0]: https://github.com/JaydenCJ/mirrordoc/releases/tag/v0.1.0
