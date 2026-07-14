"""The ``mirrordoc`` command-line interface.

Subcommands: ``check`` (discover + gate), ``diff`` (one explicit pair),
``pairs`` (list what discovery found), ``outline`` (show a file's skeleton),
and ``stamp`` (pin a mirror to the source's current commit).

Exit codes: ``0`` in sync, ``1`` drift or staleness found, ``2`` usage error.
"""

from __future__ import annotations

import argparse
import os
import posixpath
import sys
from typing import List, Optional

from . import __version__, config, pairs, report, staleness, structdiff
from .errors import MirrordocError, UsageError
from .mdparse import parse
from .outline import render_outline


def _read(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except OSError as exc:
        raise UsageError(f"cannot read {path}: {exc}") from exc


def _compare_options(cfg: config.Config, lang: str) -> structdiff.CompareOptions:
    return structdiff.CompareOptions(
        lang=lang,
        compare_code_content=cfg.compare_code_content,
        check_anchors=cfg.check_anchors,
        ignore_links=tuple(cfg.ignore_links),
    )


def _check_pair(
    root: str, pair: pairs.Pair, cfg: config.Config, stale: bool
) -> report.PairResult:
    src_abs = os.path.join(root, pair.source)
    mir_abs = os.path.join(root, pair.mirror)
    src_doc = parse(_read(src_abs))
    mir_text = _read(mir_abs)
    mir_doc = parse(mir_text)
    findings = structdiff.compare(src_doc, mir_doc, _compare_options(cfg, pair.lang))
    notes: List[str] = []
    if stale:
        stale_findings, note = staleness.check_staleness(
            src_abs, mir_abs, mir_text, require_marker=cfg.require_marker
        )
        findings.extend(stale_findings)
        if note:
            notes.append(note)
    return report.PairResult(
        source=pair.source,
        mirror=pair.mirror,
        lang=pair.lang,
        findings=findings,
        notes=notes,
    )


def _cmd_check(args: argparse.Namespace) -> int:
    root = args.root
    if not os.path.isdir(root):
        raise UsageError(f"not a directory: {root}")
    cfg = config.load_config(root, args.config)
    langs = args.langs.split(",") if args.langs else cfg.langs
    exclude = list(cfg.exclude) + list(args.exclude or [])
    if args.require_marker:
        cfg.require_marker = True
    if args.lax_code:
        cfg.compare_code_content = False
    found = pairs.discover(root, langs=langs, exclude=exclude, explicit=cfg.pairs)
    if not found:
        print("mirrordoc: no mirror pairs found", file=sys.stderr)
        return 0
    stale = cfg.check_staleness and not args.no_stale
    rep = report.Report(
        results=[_check_pair(root, p, cfg, stale) for p in found]
    )
    print(report.render(rep, args.format, __version__))
    return rep.exit_code(strict=args.strict)


def _cmd_diff(args: argparse.Namespace) -> int:
    parts = pairs.split_lang_suffix(os.path.basename(args.mirror))
    lang = args.lang or (parts[1] if parts else "und")
    cfg = config.Config(
        compare_code_content=not args.lax_code,
        ignore_links=list(args.ignore_link or []),
    )
    src_doc = parse(_read(args.source))
    mir_doc = parse(_read(args.mirror))
    findings = structdiff.compare(src_doc, mir_doc, _compare_options(cfg, lang))
    rep = report.Report(
        results=[
            report.PairResult(
                source=args.source, mirror=args.mirror, lang=lang, findings=findings
            )
        ]
    )
    print(report.render(rep, args.format, __version__))
    return rep.exit_code(strict=args.strict)


def _cmd_pairs(args: argparse.Namespace) -> int:
    root = args.root
    if not os.path.isdir(root):
        raise UsageError(f"not a directory: {root}")
    cfg = config.load_config(root, args.config)
    found = pairs.discover(
        root, langs=cfg.langs, exclude=cfg.exclude, explicit=cfg.pairs
    )
    if not found:
        print("mirrordoc: no mirror pairs found", file=sys.stderr)
        return 0
    width = max(len(p.source) for p in found)
    for p in found:
        print(f"{p.source:<{width}}  ->  {p.mirror}  [{p.lang}]")
    return 0


def _cmd_outline(args: argparse.Namespace) -> int:
    for i, path in enumerate(args.files):
        if i:
            print()
        doc = parse(_read(path))
        print(render_outline(posixpath.basename(path), doc))
    return 0


def _cmd_stamp(args: argparse.Namespace) -> int:
    mirror = args.mirror
    if not os.path.isfile(mirror):
        raise UsageError(f"not a file: {mirror}")
    if args.source:
        source = args.source
    else:
        parts = pairs.split_lang_suffix(os.path.basename(mirror))
        if parts is None:
            raise UsageError(
                "cannot infer the source from the mirror's name; pass --source"
            )
        stem, _lang, ext = parts
        source = os.path.join(os.path.dirname(mirror), stem + ext)
    if not os.path.isfile(source):
        raise UsageError(f"source file not found: {source}")
    sha = staleness.stamp(os.path.abspath(source), os.path.abspath(mirror))
    print(f"stamped {mirror} at {sha[:12]} (source: {source})")
    return 0


def _add_format_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--format",
        choices=("text", "json", "markdown"),
        default="text",
        help="output format (default: text)",
    )
    p.add_argument(
        "--strict",
        action="store_true",
        help="treat warnings as failures (exit 1)",
    )
    p.add_argument(
        "--lax-code",
        action="store_true",
        help="do not require code-block contents to be byte-identical",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mirrordoc",
        description=(
            "Keep translated Markdown mirrors structurally in sync with the "
            "canonical version — offline, in git."
        ),
    )
    parser.add_argument(
        "--version", action="version", version=f"mirrordoc {__version__}"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser(
        "check", help="discover mirror pairs under a root and gate them"
    )
    p_check.add_argument("root", nargs="?", default=".", help="directory to scan")
    p_check.add_argument("--config", default="", help="path to a .mirrordoc.json")
    p_check.add_argument(
        "--langs", default="", help="comma-separated language filter (e.g. zh,ja)"
    )
    p_check.add_argument(
        "--exclude",
        action="append",
        metavar="GLOB",
        help="exclude paths matching this glob (repeatable)",
    )
    p_check.add_argument(
        "--no-stale", action="store_true", help="skip git staleness checks"
    )
    p_check.add_argument(
        "--require-marker",
        action="store_true",
        help="fail mirrors that carry no sync marker",
    )
    _add_format_flags(p_check)
    p_check.set_defaults(func=_cmd_check)

    p_diff = sub.add_parser(
        "diff", help="compare one explicit source/mirror pair (structure only)"
    )
    p_diff.add_argument("source", help="canonical Markdown file")
    p_diff.add_argument("mirror", help="translated mirror file")
    p_diff.add_argument("--lang", default="", help="mirror language tag override")
    p_diff.add_argument(
        "--ignore-link",
        action="append",
        metavar="GLOB",
        help="ignore link URLs matching this glob (repeatable)",
    )
    _add_format_flags(p_diff)
    p_diff.set_defaults(func=_cmd_diff)

    p_pairs = sub.add_parser("pairs", help="list discovered mirror pairs")
    p_pairs.add_argument("root", nargs="?", default=".", help="directory to scan")
    p_pairs.add_argument("--config", default="", help="path to a .mirrordoc.json")
    p_pairs.set_defaults(func=_cmd_pairs)

    p_outline = sub.add_parser(
        "outline", help="print the structural skeleton mirrordoc sees"
    )
    p_outline.add_argument("files", nargs="+", help="Markdown file(s)")
    p_outline.set_defaults(func=_cmd_outline)

    p_stamp = sub.add_parser(
        "stamp", help="pin a mirror to the source's current commit"
    )
    p_stamp.add_argument("mirror", help="translated mirror file to stamp")
    p_stamp.add_argument(
        "--source", default="", help="canonical file (default: inferred from the name)"
    )
    p_stamp.set_defaults(func=_cmd_stamp)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Programmatic entry point; returns the process exit code."""
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        return args.func(args)
    except MirrordocError as exc:
        # UsageError, ConfigError, and GitError all derive from MirrordocError.
        print(f"mirrordoc: error: {exc}", file=sys.stderr)
        return 2


def run() -> None:
    """Console-script entry point."""
    raise SystemExit(main())
