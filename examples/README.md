# mirrordoc examples

`demo-docs/` is a miniature documentation tree for a fictional project,
covering both discovery conventions and both outcomes:

- `README.ja.md` — a **faithful** suffix-style mirror: prose translated,
  skeleton intact. The gate passes.
- `README.zh.md` — a **drifted** suffix-style mirror: the `## Roadmap`
  section was never translated, the Python example was localized (code must
  stay byte-identical), and the changelog link was dropped.
- `docs/ja/guide.md` — a faithful **directory-style** mirror of
  `docs/guide.md`.

Run from the repository root:

```bash
mirrordoc pairs examples/demo-docs           # what discovery finds
mirrordoc check examples/demo-docs --no-stale  # exit 1: zh has drifted
mirrordoc outline examples/demo-docs/README.md # the skeleton being compared
```

`--no-stale` keeps the example deterministic inside this repository's own
git history; in your repo you would omit it and let the staleness check run.
To see the full stamp → stale → re-stamp cycle against real commits, run
`bash scripts/smoke.sh`, which builds a throwaway repository and drives it.
