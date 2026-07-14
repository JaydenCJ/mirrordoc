"""mirrordoc — keep translated Markdown mirrors in sync with the canonical file.

Public API:

- :func:`mirrordoc.parse` — parse Markdown into its structural skeleton.
- :func:`mirrordoc.compare` — diff two skeletons into findings.
- :func:`mirrordoc.discover` — find (source, mirror) pairs under a directory.
- :func:`mirrordoc.check_staleness` / :func:`mirrordoc.stamp` — git freshness.

The command-line interface (``mirrordoc check`` and friends) is a thin layer
over these functions; everything is importable and unit-testable.
"""

from .mdparse import Document, parse
from .pairs import Pair, discover
from .staleness import check_staleness, find_marker, stamp
from .structdiff import CompareOptions, Finding, compare

__version__ = "0.1.0"

__all__ = [
    "CompareOptions",
    "Document",
    "Finding",
    "Pair",
    "__version__",
    "check_staleness",
    "compare",
    "discover",
    "find_marker",
    "parse",
    "stamp",
]
