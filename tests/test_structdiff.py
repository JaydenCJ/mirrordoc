"""Tests for the structure-comparison engine.

The contract under test: prose may differ freely between source and mirror,
but headings, code blocks, table shapes, links, and images must match.
"""

from conftest import MIRROR_DOC, SOURCE_DOC

from mirrordoc.mdparse import parse
from mirrordoc.structdiff import CompareOptions, compare, delocalize_url, worst_severity


def diff(src_text, mir_text, **opts):
    return compare(parse(src_text), parse(mir_text), CompareOptions(**opts))


def codes(findings):
    return [f.code for f in findings]


def test_faithful_translation_has_no_findings():
    # Fully translated prose, identical skeleton: the whole point of the tool.
    assert diff(SOURCE_DOC, MIRROR_DOC, lang="zh") == []
    assert diff(SOURCE_DOC, SOURCE_DOC) == []
    assert diff("# Widget\n\n## Install\n", "# 部件\n\n## 安装\n") == []


def test_missing_heading_is_reported_with_source_text():
    findings = diff("# t\n\n## Install\n\n## Usage\n", "# t\n\n## 安装\n")
    assert codes(findings) == ["heading-missing"]
    assert "Usage" in findings[0].message
    assert findings[0].severity == "error"


def test_extra_heading_in_mirror():
    findings = diff("# t\n", "# t\n\n## 额外\n")
    assert codes(findings) == ["heading-extra"]
    assert findings[0].mirror_line == 3


def test_heading_level_change_detected():
    findings = diff("# t\n\n## a\n\n## b\n", "# t\n\n### a\n\n## b\n")
    assert "heading-level" in codes(findings) or "heading-missing" in codes(findings)
    assert worst_severity(findings) == "error"


def test_code_block_count_and_translated_content_are_drift():
    missing = diff("```\na\n```\n\n```\nb\n```\n", "```\na\n```\n")
    assert "codeblock-count" in codes(missing)
    translated = diff(
        '```python\nprint("hello")\n```\n', '```python\nprint("你好")\n```\n'
    )
    assert codes(translated) == ["codeblock-drift"]
    assert "block line 1" in translated[0].message


def test_lax_code_skips_content_but_still_checks_language():
    drift = ('```python\nprint("hello")\n```\n', '```python\nprint("你好")\n```\n')
    assert diff(*drift, compare_code_content=False) == []
    findings = diff("```bash\nx\n```\n", "```sh\nx\n```\n", compare_code_content=False)
    assert codes(findings) == ["codeblock-lang"]


def test_table_column_mismatch_error_row_mismatch_warning():
    cols = diff("| a | b | c |\n|---|---|---|\n", "| a | b |\n|---|---|\n")
    assert [(f.code, f.severity) for f in cols] == [("table-shape", "error")]
    rows = diff(
        "| a | b |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n",
        "| a | b |\n|---|---|\n| 1 | 2 |\n",
    )
    assert [(f.code, f.severity) for f in rows] == [("table-rows", "warning")]


def test_missing_link_is_error_extra_link_is_warning():
    findings = diff(
        "[a](https://example.test/a)\n",
        "[b](https://example.test/b)\n",
    )
    by_code = {f.code: f.severity for f in findings}
    assert by_code == {"link-missing": "error", "link-extra": "warning"}


def test_anchor_links_ignored_by_default_flagged_when_opted_in():
    # Translated headings produce different slugs; anchors must not gate.
    assert diff("[jump](#install)\n", "[jump](#安装)\n") == []
    assert diff("[x](docs/a.md#install)\n", "[x](docs/a.md#安装)\n") == []
    strict = diff("[jump](#install)\n", "[jump](#安装)\n", check_anchors=True)
    assert set(codes(strict)) == {"link-missing", "link-extra"}


def test_ignore_links_glob():
    findings = diff(
        "[badge](https://img.shields.io/badge/a-b-c)\n",
        "no badge here\n",
        ignore_links=("https://img.shields.io/*",),
    )
    assert findings == []


def test_localized_link_equivalence_both_conventions():
    # The zh mirror may point at sibling translations; that satisfies the gate.
    assert diff("[log](CHANGELOG.md)\n", "[log](CHANGELOG.zh.md)\n", lang="zh") == []
    assert (
        diff("[guide](docs/guide.md)\n", "[guide](docs/zh/guide.md)\n", lang="zh")
        == []
    )


def test_localization_never_cancels_a_real_switcher_link():
    # Both files carry the full language switcher; nothing should cancel.
    text = "[English](README.md) | [中文](README.zh.md)\n"
    assert diff(text, text, lang="zh") == []


def test_delocalize_url_leaves_absolute_urls_alone():
    assert (
        delocalize_url("https://example.test/zh/x.md", "zh")
        == "https://example.test/zh/x.md"
    )
    assert delocalize_url("guide.zh.md", "zh") == "guide.md"


def test_image_src_mismatch_and_localized_image():
    findings = diff("![d](a.svg)\n", "![d](b.svg)\n")
    assert set(codes(findings)) == {"image-missing", "image-extra"}
    assert all(f.severity == "error" for f in findings)
    assert diff("![d](docs/shot.png)\n", "![d](docs/zh/shot.png)\n", lang="zh") == []


def test_list_item_count_mismatch_is_warning():
    findings = diff("- a\n- b\n- c\n", "- a\n- b\n")
    assert codes(findings) == ["list-items"]
    assert findings[0].severity == "warning"


def test_worst_severity_ranks_errors_over_warnings():
    findings = diff("- a\n- b\n\n[x](y.md)\n", "- a\n")
    assert worst_severity(findings) == "error"
    assert worst_severity([]) is None


def test_multiple_drifts_reported_together():
    src = "# t\n\n## a\n\n```bash\nx\n```\n\n[l](https://example.test/)\n"
    mir = "# t\n\n```bash\ny\n```\n"
    got = set(codes(diff(src, mir)))
    assert {"heading-missing", "codeblock-drift", "link-missing"} <= got
