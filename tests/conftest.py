"""Shared fixtures for the mirrordoc test suite.

The suite is fully offline and deterministic: documents are written into
``tmp_path``, git repositories (for the staleness tests) are created locally
with a fixed identity and fixed commit dates, and the CLI is driven
in-process so exit codes and output can be asserted without spawning
interpreters.
"""

import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mirrordoc.cli import main  # noqa: E402  (path bootstrap must run first)

# Fixed, increasing commit dates keep %ct comparisons deterministic.
_BASE_DATE = 1750000000


@pytest.fixture
def run_cli(monkeypatch, capsys):
    """Invoke ``mirrordoc`` in-process; returns ``(exit_code, stdout, stderr)``."""

    def _run(argv, cwd=None):
        if cwd is not None:
            monkeypatch.chdir(cwd)
        code = main([str(a) for a in argv])
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return _run


def git(*args, cwd, date_offset=0):
    """Run a git command with a fixed identity and clock; returns stdout."""
    stamp = f"{_BASE_DATE + date_offset} +0000"
    env = dict(
        os.environ,
        GIT_AUTHOR_NAME="mirrordoc-tests",
        GIT_AUTHOR_EMAIL="tests@example.test",
        GIT_COMMITTER_NAME="mirrordoc-tests",
        GIT_COMMITTER_EMAIL="tests@example.test",
        GIT_AUTHOR_DATE=stamp,
        GIT_COMMITTER_DATE=stamp,
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_CONFIG_SYSTEM=os.devnull,
        HOME=str(cwd),
    )
    proc = subprocess.run(
        ["git", *args], cwd=str(cwd), env=env, capture_output=True, text=True
    )
    assert proc.returncode == 0, f"git {args} failed: {proc.stderr}"
    return proc.stdout


@pytest.fixture
def git_repo(tmp_path):
    """An initialized git repository (branch ``main``) in ``tmp_path``."""
    git("init", "-q", "-b", "main", cwd=tmp_path)
    return tmp_path


def commit_file(repo, relpath, content, message="update", date_offset=0):
    """Write ``content`` to ``relpath`` and commit it at a fixed date."""
    path = repo / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    git("add", str(relpath), cwd=repo)
    git("commit", "-q", "-m", message, cwd=repo, date_offset=date_offset)
    return path


SOURCE_DOC = """# widget

[English](README.md) | [中文](README.zh.md)

Widget makes things.

## Install

```bash
pip install widget
```

## Options

| Key | Default |
|---|---|
| `size` | `3` |
| `mode` | `fast` |

- point one
- point two

![Demo](docs/demo.svg)
"""

# A faithful Chinese mirror of SOURCE_DOC: prose translated, structure kept.
MIRROR_DOC = """# widget

[English](README.md) | [中文](README.zh.md)

Widget 用来制作东西。

## 安装

```bash
pip install widget
```

## 选项

| 键 | 默认值 |
|---|---|
| `size` | `3` |
| `mode` | `fast` |

- 第一点
- 第二点

![Demo](docs/demo.svg)
"""
