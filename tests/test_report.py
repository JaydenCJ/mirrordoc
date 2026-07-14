"""Tests for the report model and the three renderers.

The invariant that matters: one Report object, three formats, one verdict.
"""

import json

from mirrordoc.report import PairResult, Report, render_json, render_markdown, render_text
from mirrordoc.structdiff import Finding


def make_report():
    return Report(
        results=[
            PairResult(
                source="README.md",
                mirror="README.zh.md",
                lang="zh",
                findings=[
                    Finding(
                        code="heading-missing",
                        severity="error",
                        message='mirror is missing a level-2 heading: "Roadmap"',
                        source_line=30,
                    ),
                    Finding(
                        code="list-items",
                        severity="warning",
                        message="source has 2 list items, mirror has 0",
                    ),
                ],
            ),
            PairResult(
                source="README.md",
                mirror="README.ja.md",
                lang="ja",
                notes=["staleness skipped: not inside a git repository"],
            ),
        ]
    )


def test_exit_codes_clean_vs_errors():
    rep = Report(results=[PairResult(source="a.md", mirror="a.zh.md", lang="zh")])
    assert rep.exit_code() == 0
    assert make_report().exit_code() == 1


def test_warnings_pass_unless_strict():
    rep = Report(
        results=[
            PairResult(
                source="a.md",
                mirror="a.zh.md",
                lang="zh",
                findings=[Finding(code="list-items", severity="warning", message="m")],
            )
        ]
    )
    assert rep.exit_code() == 0
    assert rep.exit_code(strict=True) == 1


def test_text_render_contains_findings_and_verdict():
    out = render_text(make_report())
    assert "README.md <-> README.zh.md [zh]" in out
    assert "heading-missing" in out
    assert "in sync" in out  # the clean ja pair
    assert out.strip().endswith("FAIL: 1 error(s), 1 warning(s) across 2 pair(s)")


def test_text_render_ok_verdict_when_clean():
    rep = Report(results=[PairResult(source="a.md", mirror="a.ja.md", lang="ja")])
    assert "OK: 0 error(s)" in render_text(rep)


def test_json_render_is_valid_and_schema_versioned():
    payload = json.loads(render_json(make_report(), "0.1.0"))
    assert payload["schema_version"] == 1
    assert payload["tool"] == "mirrordoc"
    assert payload["version"] == "0.1.0"
    assert payload["summary"] == {"errors": 1, "infos": 0, "pairs": 2, "warnings": 1}
    zh = payload["pairs"][0]
    assert zh["in_sync"] is False
    assert zh["findings"][0]["code"] == "heading-missing"
    assert zh["findings"][0]["source_line"] == 30


def test_json_keys_are_sorted_for_stable_diffs():
    out = render_json(make_report(), "0.1.0")
    assert out == render_json(make_report(), "0.1.0")
    top_keys = list(json.loads(out).keys())
    assert top_keys == sorted(top_keys)


def test_markdown_render_has_table_and_escapes_pipes():
    rep = make_report()
    rep.results[0].findings.append(
        Finding(code="table-shape", severity="error", message="a | b differs")
    )
    out = render_markdown(rep)
    assert "## mirrordoc report" in out
    assert "| error | `heading-missing` |" in out
    assert "a \\| b differs" in out
    assert "✅ in sync" in out
    clean = Report(results=[PairResult(source="a.md", mirror="a.zh.md", lang="zh")])
    assert "structurally in sync" in render_markdown(clean)
