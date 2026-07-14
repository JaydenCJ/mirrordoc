"""Configuration loading for ``.mirrordoc.json``.

JSON was chosen deliberately: it parses identically on every supported
Python (3.9+) with zero dependencies, and a mirror-parity config rarely
needs comments. Unknown keys are rejected loudly — a typoed option that
silently does nothing is worse than an error.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, fields
from typing import Any, Dict, List

from .errors import ConfigError

CONFIG_FILENAME = ".mirrordoc.json"


@dataclass
class Config:
    """Effective settings after merging defaults, file, and CLI flags."""

    langs: List[str] = field(default_factory=list)
    exclude: List[str] = field(default_factory=list)
    pairs: List[Dict[str, str]] = field(default_factory=list)
    ignore_links: List[str] = field(default_factory=list)
    compare_code_content: bool = True
    check_anchors: bool = False
    check_staleness: bool = True
    require_marker: bool = False


_STR_LIST_KEYS = {"langs", "exclude", "ignore_links"}
_BOOL_KEYS = {
    "compare_code_content",
    "check_anchors",
    "check_staleness",
    "require_marker",
}


def _validate_str_list(key: str, value: Any) -> List[str]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ConfigError(f"config key {key!r} must be a list of strings")
    return list(value)


def _validate_pairs(value: Any) -> List[Dict[str, str]]:
    if not isinstance(value, list):
        raise ConfigError("config key 'pairs' must be a list of objects")
    out: List[Dict[str, str]] = []
    for entry in value:
        if not isinstance(entry, dict):
            raise ConfigError("each entry in 'pairs' must be an object")
        unknown = set(entry) - {"source", "mirror", "lang"}
        if unknown:
            raise ConfigError(
                f"unknown key(s) in a 'pairs' entry: {', '.join(sorted(unknown))}"
            )
        for req in ("source", "mirror"):
            if not isinstance(entry.get(req), str) or not entry[req]:
                raise ConfigError(f"each 'pairs' entry needs a string {req!r}")
        if "lang" in entry and not isinstance(entry["lang"], str):
            raise ConfigError("'lang' in a 'pairs' entry must be a string")
        out.append({k: entry[k] for k in ("source", "mirror", "lang") if k in entry})
    return out


def parse_config(raw: Any, origin: str) -> Config:
    """Validate a decoded JSON document into a :class:`Config`."""
    if not isinstance(raw, dict):
        raise ConfigError(f"{origin}: top level must be a JSON object")
    known = {f.name for f in fields(Config)}
    unknown = set(raw) - known
    if unknown:
        raise ConfigError(
            f"{origin}: unknown config key(s): {', '.join(sorted(unknown))}"
        )
    cfg = Config()
    for key, value in raw.items():
        if key in _STR_LIST_KEYS:
            setattr(cfg, key, _validate_str_list(key, value))
        elif key in _BOOL_KEYS:
            if not isinstance(value, bool):
                raise ConfigError(f"{origin}: config key {key!r} must be a boolean")
            setattr(cfg, key, value)
        elif key == "pairs":
            cfg.pairs = _validate_pairs(value)
    return cfg


def load_config(root: str, explicit_path: str = "") -> Config:
    """Load config from ``explicit_path``, or ``<root>/.mirrordoc.json``, or defaults."""
    path = explicit_path or os.path.join(root, CONFIG_FILENAME)
    if not os.path.isfile(path):
        if explicit_path:
            raise ConfigError(f"config file not found: {explicit_path}")
        return Config()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path}: invalid JSON — {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"{path}: {exc}") from exc
    return parse_config(raw, path)
