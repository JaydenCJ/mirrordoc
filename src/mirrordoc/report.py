"""Report model and the three renderers (text, JSON, Markdown).

One :class:`Report` object feeds all three formats, so the verdict can never
differ between what a human reads in the terminal, what a script parses from
JSON, and what lands in a PR comment.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import List

from .structdiff import Finding

SCHEMA_VERSION = 1


@dataclass
class PairResult:
    """Everything mirrordoc concluded about one (source, mirror) pair."""

    source: str
    mirror: str
    lang: str
    findings: List[Finding] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


@dataclass
class Report:
    """Results for every checked pair, in deterministic order."""

    results: List[PairResult] = field(default_factory=list)

    def count(self, severity: str) -> int:
        return sum(
            1 for r in self.results for f in r.findings if f.severity == severity
        )

    def exit_code(self, strict: bool = False) -> int:
        """0 when the gate passes; 1 when it fails.

        Errors always fail; ``strict`` promotes warnings to failures too.
        """
        if self.count("error"):
            return 1
        if strict and self.count("warning"):
            return 1
        return 0


_SEV_TAG = {"error": "ERROR", "warning": "WARN ", "info": "INFO "}


def render_text(report: Report) -> str:
    """Aligned, grep-friendly terminal output."""
    lines: List[str] = []
    for r in report.results:
        lines.append(f"{r.source} <-> {r.mirror} [{r.lang}]")
        for note in r.notes:
            lines.append(f"  note: {note}")
        if not r.findings:
            lines.append("  in sync")
        for f in r.findings:
            lines.append(f"  {_SEV_TAG[f.severity]} {f.code:<22} {f.message}")
        lines.append("")
    errors, warnings = report.count("error"), report.count("warning")
    pairs = len(report.results)
    verdict = "FAIL" if errors else "OK"
    lines.append(
        f"{verdict}: {errors} error(s), {warnings} warning(s) "
        f"across {pairs} pair(s)"
    )
    return "\n".join(lines)


def render_json(report: Report, version: str) -> str:
    """Schema-versioned JSON with sorted keys, for tooling."""
    payload = {
        "schema_version": SCHEMA_VERSION,
        "tool": "mirrordoc",
        "version": version,
        "pairs": [
            {
                "source": r.source,
                "mirror": r.mirror,
                "lang": r.lang,
                "in_sync": not r.findings,
                "notes": list(r.notes),
                "findings": [
                    {
                        "code": f.code,
                        "severity": f.severity,
                        "message": f.message,
                        "source_line": f.source_line,
                        "mirror_line": f.mirror_line,
                    }
                    for f in r.findings
                ],
            }
            for r in report.results
        ],
        "summary": {
            "pairs": len(report.results),
            "errors": report.count("error"),
            "warnings": report.count("warning"),
            "infos": report.count("info"),
        },
    }
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)


def render_markdown(report: Report) -> str:
    """A fragment ready to paste into a pull-request comment."""
    lines: List[str] = ["## mirrordoc report", ""]
    errors, warnings = report.count("error"), report.count("warning")
    if errors:
        lines.append(
            f"**{errors} error(s), {warnings} warning(s)** "
            f"across {len(report.results)} pair(s)."
        )
    else:
        lines.append(
            f"All {len(report.results)} pair(s) structurally in sync "
            f"({warnings} warning(s))."
        )
    lines.append("")
    for r in report.results:
        lines.append(f"### `{r.source}` ↔ `{r.mirror}` ({r.lang})")
        lines.append("")
        for note in r.notes:
            lines.append(f"> {note}")
            lines.append("")
        if not r.findings:
            lines.append("- ✅ in sync")
            lines.append("")
            continue
        lines.append("| Severity | Code | Detail |")
        lines.append("|---|---|---|")
        for f in r.findings:
            detail = f.message.replace("|", "\\|")
            lines.append(f"| {f.severity} | `{f.code}` | {detail} |")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render(report: Report, fmt: str, version: str) -> str:
    """Dispatch on ``fmt`` (``text`` / ``json`` / ``markdown``)."""
    if fmt == "json":
        return render_json(report, version)
    if fmt == "markdown":
        return render_markdown(report)
    return render_text(report)
