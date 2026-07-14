"""Tests for mirror-pair discovery.

False positives are the enemy here: a version suffix or a directory that
happens to be two letters must never be treated as a translation.
"""

import pytest

from mirrordoc.errors import ConfigError
from mirrordoc.pairs import discover, is_lang_tag, lang_base, split_lang_suffix


def make(tmp_path, *relpaths):
    for rel in relpaths:
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {rel}\n", encoding="utf-8")
    return tmp_path


def as_tuples(pairs):
    return [(p.source, p.mirror, p.lang) for p in pairs]


def test_suffix_convention_discovered_deterministically(tmp_path):
    root = make(tmp_path, "README.md", "README.zh.md", "README.ja.md")
    assert as_tuples(discover(str(root))) == [
        ("README.md", "README.ja.md", "ja"),
        ("README.md", "README.zh.md", "zh"),
    ]
    assert discover(str(root)) == discover(str(root))


def test_region_subtag_accepted(tmp_path):
    root = make(tmp_path, "README.md", "README.zh-CN.md", "README.pt_BR.md")
    langs = {p.lang for p in discover(str(root))}
    assert langs == {"zh-CN", "pt_BR"}


def test_non_mirrors_are_never_paired(tmp_path):
    # "old"/"v2" are not ISO 639-1, "qq" is two letters but no language,
    # and an orphaned mirror without its canonical pairs with nothing.
    root = make(
        tmp_path, "README.md", "README.old.md", "notes.v2.md", "README.qq.md", "solo.zh.md"
    )
    assert discover(str(root)) == []


def test_directory_convention_discovered(tmp_path):
    root = make(tmp_path, "docs/guide.md", "docs/ja/guide.md", "docs/zh/guide.md")
    assert as_tuples(discover(str(root))) == [
        ("docs/guide.md", "docs/ja/guide.md", "ja"),
        ("docs/guide.md", "docs/zh/guide.md", "zh"),
    ]


def test_nested_directory_convention(tmp_path):
    root = make(tmp_path, "docs/api/http.md", "docs/ja/api/http.md")
    assert as_tuples(discover(str(root))) == [
        ("docs/api/http.md", "docs/ja/api/http.md", "ja")
    ]


def test_langs_filter_matches_primary_subtag(tmp_path):
    root = make(tmp_path, "README.md", "README.zh-CN.md", "README.ja.md")
    got = discover(str(root), langs=["zh"])
    assert as_tuples(got) == [("README.md", "README.zh-CN.md", "zh-CN")]


def test_exclude_globs_and_default_dirs_are_pruned(tmp_path):
    root = make(
        tmp_path,
        "README.md",
        "README.zh.md",
        "drafts/x.md",
        "drafts/x.zh.md",
        "node_modules/pkg/README.md",
        "node_modules/pkg/README.zh.md",
    )
    got = discover(str(root), exclude=["drafts/*"])
    assert as_tuples(got) == [("README.md", "README.zh.md", "zh")]


def test_explicit_pairs_from_config(tmp_path):
    root = make(tmp_path, "manual.md", "manual-chinese.md", "a.md", "a.ja.md")
    got = discover(
        str(root),
        explicit=[
            {"source": "manual.md", "mirror": "manual-chinese.md", "lang": "zh"},
            {"source": "a.md", "mirror": "a.ja.md"},  # lang inferred: ja
        ],
    )
    assert ("manual.md", "manual-chinese.md", "zh") in as_tuples(got)
    assert ("a.md", "a.ja.md", "ja") in as_tuples(got)


def test_explicit_pair_missing_file_raises(tmp_path):
    root = make(tmp_path, "manual.md")
    with pytest.raises(ConfigError):
        discover(str(root), explicit=[{"source": "manual.md", "mirror": "gone.md"}])


def test_a_mirror_is_never_also_a_source(tmp_path):
    # README.zh.md must not become the "source" of a deeper variant.
    root = make(tmp_path, "README.md", "README.zh.md", "zh/README.md")
    sources = {p.source for p in discover(str(root))}
    assert "README.zh.md" not in sources


def test_language_tag_helpers():
    assert is_lang_tag("zh") and is_lang_tag("zh-CN") and is_lang_tag("zh-Hans")
    assert not is_lang_tag("qq") and not is_lang_tag("v2") and not is_lang_tag("en-")
    assert lang_base("zh-CN") == "zh"
    assert lang_base("JA") == "ja"
    assert split_lang_suffix("README.zh-CN.md") == ("README", "zh-CN", ".md")
    assert split_lang_suffix("guide.ja.markdown") == ("guide", "ja", ".markdown")
    assert split_lang_suffix("README.md") is None
    assert split_lang_suffix("archive.old.md") is None
