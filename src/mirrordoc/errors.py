"""Exception hierarchy for mirrordoc.

Every error the CLI turns into exit code 2 derives from :class:`UsageError`;
:class:`GitError` wraps failures of the (optional) local ``git`` subprocess so
callers can degrade gracefully when a tree is not a repository.
"""


class MirrordocError(Exception):
    """Base class for all mirrordoc errors."""


class UsageError(MirrordocError):
    """Bad invocation, unreadable input, or invalid configuration (exit 2)."""


class ConfigError(UsageError):
    """A ``.mirrordoc.json`` file is malformed or contains unknown keys."""


class GitError(MirrordocError):
    """A local ``git`` invocation failed or the binary is unavailable."""
