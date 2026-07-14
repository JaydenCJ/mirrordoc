"""Tests for `.mirrordoc.json` loading and strict validation."""

import pytest

from mirrordoc.config import Config, load_config, parse_config
from mirrordoc.errors import ConfigError


def write_config(tmp_path, text, name=".mirrordoc.json"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_defaults_without_a_config_file(tmp_path):
    cfg = load_config(str(tmp_path))
    assert cfg == Config()
    assert cfg.compare_code_content is True
    assert cfg.check_staleness is True


def test_valid_config_round_trip(tmp_path):
    write_config(
        tmp_path,
        '{"langs": ["zh", "ja"], "exclude": ["drafts/*"],'
        ' "ignore_links": ["https://img.shields.io/*"],'
        ' "require_marker": true}',
    )
    cfg = load_config(str(tmp_path))
    assert cfg.langs == ["zh", "ja"]
    assert cfg.exclude == ["drafts/*"]
    assert cfg.ignore_links == ["https://img.shields.io/*"]
    assert cfg.require_marker is True


def test_explicit_pairs_validated(tmp_path):
    write_config(
        tmp_path,
        '{"pairs": [{"source": "manual.md", "mirror": "manual-zh.md", "lang": "zh"}]}',
    )
    cfg = load_config(str(tmp_path))
    assert cfg.pairs == [
        {"source": "manual.md", "mirror": "manual-zh.md", "lang": "zh"}
    ]


def test_unknown_keys_are_rejected(tmp_path):
    write_config(tmp_path, '{"lang": ["zh"]}')  # typo of "langs"
    with pytest.raises(ConfigError, match="unknown config key"):
        load_config(str(tmp_path))
    with pytest.raises(ConfigError, match="unknown key"):
        parse_config(
            {"pairs": [{"source": "a.md", "mirror": "b.md", "language": "zh"}]}, "x"
        )


def test_wrong_types_are_rejected():
    with pytest.raises(ConfigError, match="list of strings"):
        parse_config({"langs": "zh"}, "x")
    with pytest.raises(ConfigError, match="boolean"):
        parse_config({"check_anchors": "yes"}, "x")
    with pytest.raises(ConfigError, match="JSON object"):
        parse_config(["zh"], "x")


def test_invalid_json_is_a_config_error(tmp_path):
    write_config(tmp_path, "{not json}")
    with pytest.raises(ConfigError, match="invalid JSON"):
        load_config(str(tmp_path))


def test_missing_explicit_config_path_errors(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(str(tmp_path), explicit_path=str(tmp_path / "nope.json"))
