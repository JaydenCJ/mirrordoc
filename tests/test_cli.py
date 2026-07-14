"""End-to-end tests for the CLI, driven in-process.

Exit codes are part of the public contract (0 sync, 1 drift, 2 usage), so
every command is asserted on code + output together.
"""

import json

import pytest

from conftest import MIRROR_DOC, SOURCE_DOC, commit_file

from mirrordoc import __version__
from mirrordoc.cli import main


def write(root, rel, text):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def synced_tree(tmp_path):
    write(tmp_path, "README.md", SOURCE_DOC)
    write(tmp_path, "README.zh.md", MIRROR_DOC)
    return tmp_path


@pytest.fixture
def drifted_tree(tmp_path):
    write(tmp_path, "README.md", SOURCE_DOC)
    write(tmp_path, "README.zh.md", MIRROR_DOC.replace("## 选项", "### 选项"))
    return tmp_path


def test_version_flag():
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0


def test_check_in_sync_exits_zero(run_cli, synced_tree):
    code, out, _ = run_cli(["check", str(synced_tree), "--no-stale"])
    assert code == 0
    assert "in sync" in out
    assert "OK: 0 error(s)" in out


def test_check_drift_exits_one_with_findings(run_cli, drifted_tree):
    code, out, _ = run_cli(["check", str(drifted_tree), "--no-stale"])
    assert code == 1
    assert "FAIL" in out


def test_check_edge_invocations(run_cli, tmp_path):
    write(tmp_path, "README.md", "# only canonical\n")
    code, _, err = run_cli(["check", str(tmp_path)])
    assert code == 0 and "no mirror pairs found" in err
    code, _, err = run_cli(["check", str(tmp_path / "missing")])
    assert code == 2 and "not a directory" in err


def test_check_json_and_markdown_formats(run_cli, drifted_tree):
    code, out, _ = run_cli(
        ["check", str(drifted_tree), "--no-stale", "--format", "json"]
    )
    payload = json.loads(out)
    assert code == 1
    assert payload["version"] == __version__
    assert payload["summary"]["errors"] >= 1
    code, out, _ = run_cli(
        ["check", str(drifted_tree), "--no-stale", "--format", "markdown"]
    )
    assert code == 1
    assert out.startswith("## mirrordoc report")


def test_check_strict_promotes_warnings(run_cli, tmp_path):
    write(tmp_path, "a.md", "- one\n- two\n")
    write(tmp_path, "a.zh.md", "- 一\n")
    assert run_cli(["check", str(tmp_path), "--no-stale"])[0] == 0
    assert run_cli(["check", str(tmp_path), "--no-stale", "--strict"])[0] == 1


def test_check_lax_code_flag(run_cli, tmp_path):
    write(tmp_path, "a.md", "```py\nprint('hi')\n```\n")
    write(tmp_path, "a.zh.md", "```py\nprint('你好')\n```\n")
    assert run_cli(["check", str(tmp_path), "--no-stale"])[0] == 1
    assert run_cli(["check", str(tmp_path), "--no-stale", "--lax-code"])[0] == 0


def test_check_langs_filter(run_cli, tmp_path):
    write(tmp_path, "a.md", "# t\n")
    write(tmp_path, "a.zh.md", "# t\n\n## extra\n")  # drifted
    write(tmp_path, "a.ja.md", "# t\n")  # clean
    assert run_cli(["check", str(tmp_path), "--no-stale", "--langs", "ja"])[0] == 0
    assert run_cli(["check", str(tmp_path), "--no-stale", "--langs", "zh"])[0] == 1


def test_check_reads_config_from_root_and_rejects_bad_config(run_cli, tmp_path):
    write(tmp_path, "drafts/b.md", "# b\n")
    write(tmp_path, "drafts/b.zh.md", "# b\n\n## drifted\n")
    write(tmp_path, ".mirrordoc.json", '{"exclude": ["drafts/*"]}')
    code, _, err = run_cli(["check", str(tmp_path), "--no-stale"])
    assert code == 0
    assert "no mirror pairs found" in err
    write(tmp_path, ".mirrordoc.json", '{"nope": 1}')
    code, _, err = run_cli(["check", str(tmp_path)])
    assert code == 2
    assert "unknown config key" in err


def test_diff_explicit_pair_and_missing_file(run_cli, tmp_path):
    src = write(tmp_path, "README.md", SOURCE_DOC)
    mir = write(tmp_path, "README.zh.md", MIRROR_DOC)
    code, out, _ = run_cli(["diff", str(src), str(mir)])
    assert code == 0
    assert "in sync" in out
    code, _, err = run_cli(["diff", str(src), str(tmp_path / "gone.md")])
    assert code == 2
    assert "cannot read" in err


def test_diff_infers_lang_from_suffix(run_cli, tmp_path):
    # zh-localized changelog link only passes if the lang was inferred.
    src = write(tmp_path, "README.md", "[log](CHANGELOG.md)\n")
    mir = write(tmp_path, "README.zh.md", "[log](CHANGELOG.zh.md)\n")
    assert run_cli(["diff", str(src), str(mir)])[0] == 0


def test_diff_ignore_link_flag(run_cli, tmp_path):
    src = write(tmp_path, "a.md", "[badge](https://img.shields.io/x)\n")
    mir = write(tmp_path, "a.zh.md", "plain\n")
    assert run_cli(["diff", str(src), str(mir)])[0] == 1
    assert (
        run_cli(
            ["diff", str(src), str(mir), "--ignore-link", "https://img.shields.io/*"]
        )[0]
        == 0
    )


def test_pairs_lists_discovered_pairs(run_cli, synced_tree):
    code, out, _ = run_cli(["pairs", str(synced_tree)])
    assert code == 0
    assert "README.md" in out and "README.zh.md" in out and "[zh]" in out


def test_outline_prints_heading_tree(run_cli, synced_tree):
    code, out, _ = run_cli(["outline", str(synced_tree / "README.md")])
    assert code == 0
    assert "H1 widget" in out
    assert "H2 Install" in out
    assert "code blocks" in out


def test_stamp_then_check_is_fresh_then_stale(run_cli, git_repo):
    commit_file(git_repo, "README.md", SOURCE_DOC, date_offset=0)
    commit_file(git_repo, "README.zh.md", MIRROR_DOC, date_offset=10)
    code, out, _ = run_cli(["stamp", str(git_repo / "README.zh.md")])
    assert code == 0
    assert "stamped" in out
    commit_file(
        git_repo,
        "README.zh.md",
        (git_repo / "README.zh.md").read_text(encoding="utf-8"),
        message="stamp",
        date_offset=20,
    )
    assert run_cli(["check", str(git_repo)])[0] == 0
    # The canonical file moves on; the stamped mirror is now stale.
    commit_file(git_repo, "README.md", SOURCE_DOC + "\nmore prose\n", date_offset=30)
    code, out, _ = run_cli(["check", str(git_repo)])
    assert code == 1
    assert "stale-marker" in out


def test_stamp_requires_inferable_source(run_cli, tmp_path):
    path = write(tmp_path, "translated.md", "# t\n")
    write(tmp_path, "canonical.md", "# t\n")
    code, _, err = run_cli(["stamp", str(path)])
    assert code == 2
    assert "--source" in err


def test_check_shipped_example_docs(run_cli):
    # The repository's own examples/demo-docs must behave as documented:
    # ja in sync, zh deliberately drifted.
    import os

    root = os.path.join(os.path.dirname(__file__), "..", "examples", "demo-docs")
    code, out, _ = run_cli(["check", root, "--no-stale"])
    assert code == 1
    assert "README.ja.md [ja]" in out
    assert "heading-missing" in out
    assert "codeblock-drift" in out
