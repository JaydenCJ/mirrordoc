"""Tests for git-based staleness detection and the sync marker.

Real git repositories are created in ``tmp_path`` with fixed commit dates,
so timestamp comparisons are deterministic and no network is involved.
"""

import pytest

from conftest import commit_file

from mirrordoc.errors import UsageError
from mirrordoc.staleness import check_staleness, find_marker, stamp


def codes(findings):
    return [f.code for f in findings]


def check(repo, source="README.md", mirror="README.zh.md", **kw):
    mirror_text = (repo / mirror).read_text(encoding="utf-8")
    return check_staleness(
        str(repo / source), str(repo / mirror), mirror_text, **kw
    )


# -- marker parsing -----------------------------------------------------------


def test_find_marker_parses_source_commit_and_line():
    text = "<!-- mirrordoc: source=README.md commit=0123abc -->\n# t\n"
    marker = find_marker(text)
    assert (marker.source, marker.commit, marker.line) == ("README.md", "0123abc", 1)
    assert find_marker("<!--mirrordoc:source=a.md commit=abcdef0-->\n") is not None


def test_find_marker_rejects_plain_files_and_bad_hex():
    assert find_marker("# plain file\n") is None
    assert find_marker("<!-- mirrordoc: source=a.md commit=xyz -->\n") is None


# -- stamp --------------------------------------------------------------------


def test_stamp_inserts_marker_and_replaces_existing_one(git_repo):
    commit_file(git_repo, "README.md", "# t\n", date_offset=0)
    commit_file(git_repo, "README.zh.md", "# t\n", date_offset=10)
    sha = stamp(str(git_repo / "README.md"), str(git_repo / "README.zh.md"))
    marker = find_marker((git_repo / "README.zh.md").read_text(encoding="utf-8"))
    assert marker.commit == sha and len(sha) == 40
    assert marker.source == "README.md"
    # A second stamp must replace, not duplicate, the marker.
    stamp(str(git_repo / "README.md"), str(git_repo / "README.zh.md"))
    text = (git_repo / "README.zh.md").read_text(encoding="utf-8")
    assert text.count("mirrordoc:") == 1


def test_stamp_uses_mirror_relative_source_path(git_repo):
    commit_file(git_repo, "docs/guide.md", "# g\n", date_offset=0)
    commit_file(git_repo, "docs/ja/guide.md", "# g\n", date_offset=10)
    stamp(str(git_repo / "docs/guide.md"), str(git_repo / "docs/ja/guide.md"))
    marker = find_marker((git_repo / "docs/ja/guide.md").read_text(encoding="utf-8"))
    assert marker.source == "../guide.md"


def test_stamp_refuses_non_repos_and_uncommitted_sources(git_repo, tmp_path):
    (tmp_path / "a.md").write_text("# a\n", encoding="utf-8")
    (tmp_path / "a.zh.md").write_text("# a\n", encoding="utf-8")
    with pytest.raises(UsageError):
        stamp(str(tmp_path / "a.md"), str(tmp_path / "a.zh.md"))
    (git_repo / "a.md").write_text("# a\n", encoding="utf-8")
    commit_file(git_repo, "a.zh.md", "# a\n")
    with pytest.raises(UsageError):
        stamp(str(git_repo / "a.md"), str(git_repo / "a.zh.md"))


# -- check_staleness ----------------------------------------------------------


def test_fresh_marker_yields_no_findings(git_repo):
    commit_file(git_repo, "README.md", "# t\n", date_offset=0)
    commit_file(git_repo, "README.zh.md", "# t\n", date_offset=10)
    stamp(str(git_repo / "README.md"), str(git_repo / "README.zh.md"))
    commit_file(
        git_repo,
        "README.zh.md",
        (git_repo / "README.zh.md").read_text(encoding="utf-8"),
        message="stamp",
        date_offset=20,
    )
    findings, note = check(git_repo)
    assert findings == [] and note is None


def test_source_commit_after_stamp_is_stale_error(git_repo):
    commit_file(git_repo, "README.md", "# t\n", date_offset=0)
    commit_file(git_repo, "README.zh.md", "# t\n", date_offset=10)
    stamp(str(git_repo / "README.md"), str(git_repo / "README.zh.md"))
    commit_file(git_repo, "README.md", "# t\n\nnew section\n", date_offset=20)
    findings, _ = check(git_repo)
    assert codes(findings) == ["stale-marker"]
    assert findings[0].severity == "error"
    assert "1 commit(s)" in findings[0].message


def test_unrelated_commits_do_not_stale_the_marker(git_repo):
    # Commits that never touch the source must not trip the gate.
    commit_file(git_repo, "README.md", "# t\n", date_offset=0)
    commit_file(git_repo, "README.zh.md", "# t\n", date_offset=10)
    stamp(str(git_repo / "README.md"), str(git_repo / "README.zh.md"))
    commit_file(git_repo, "unrelated.txt", "noise\n", date_offset=20)
    findings, _ = check(git_repo)
    assert "stale-marker" not in codes(findings)


def test_marker_source_mismatch_is_warned(git_repo):
    commit_file(git_repo, "README.md", "# t\n", date_offset=0)
    commit_file(git_repo, "OTHER.md", "# o\n", date_offset=5)
    commit_file(git_repo, "README.zh.md", "# t\n", date_offset=10)
    stamp(str(git_repo / "OTHER.md"), str(git_repo / "README.zh.md"))
    findings, _ = check(git_repo)
    assert "marker-source-mismatch" in codes(findings)


def test_unknown_stamped_commit_warns_and_falls_back(git_repo):
    commit_file(git_repo, "README.md", "# t\n", date_offset=20)
    commit_file(
        git_repo,
        "README.zh.md",
        "<!-- mirrordoc: source=README.md commit=deadbeefdeadbeefdeadbeefdeadbeefdeadbeef -->\n# t\n",
        date_offset=10,
    )
    findings, _ = check(git_repo)
    assert "marker-unknown-commit" in codes(findings)
    assert "stale-commit" in codes(findings)  # fell back to dates


def test_without_marker_newer_source_warns_older_source_is_clean(git_repo):
    commit_file(git_repo, "README.zh.md", "# t\n", date_offset=0)
    commit_file(git_repo, "README.md", "# t updated\n", date_offset=100)
    findings, _ = check(git_repo)
    assert [(f.code, f.severity) for f in findings] == [("stale-commit", "warning")]
    # Now the mirror catches up; the pair is clean again.
    commit_file(git_repo, "README.zh.md", "# t 已更新\n", date_offset=200)
    findings, note = check(git_repo)
    assert findings == [] and note is None


def test_require_marker_flags_unstamped_mirror(git_repo):
    commit_file(git_repo, "README.md", "# t\n", date_offset=0)
    commit_file(git_repo, "README.zh.md", "# t\n", date_offset=10)
    findings, _ = check(git_repo, require_marker=True)
    assert "marker-missing" in codes(findings)


def test_outside_a_repo_staleness_is_skipped_with_note(tmp_path):
    (tmp_path / "a.md").write_text("# a\n", encoding="utf-8")
    (tmp_path / "a.zh.md").write_text("# a\n", encoding="utf-8")
    findings, note = check_staleness(
        str(tmp_path / "a.md"), str(tmp_path / "a.zh.md"), "# a\n"
    )
    assert findings == [] and "not inside a git repository" in note


def test_uncommitted_source_is_skipped_with_note(git_repo):
    (git_repo / "a.md").write_text("# a\n", encoding="utf-8")
    commit_file(git_repo, "a.zh.md", "# a\n")
    findings, note = check(git_repo, source="a.md", mirror="a.zh.md")
    assert findings == [] and "no commits yet" in note
