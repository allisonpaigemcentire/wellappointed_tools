"""Command line for agentdebug."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agentdebug.lint import Finding, lint_path
from agentdebug.report import init_report
from agentdebug.trace import format_text, summarize_path


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "report":
            return _report_init(args)
        if args.command == "lint":
            return _lint(args)
        if args.command == "trace":
            return _trace_summarize(args)
    except FileNotFoundError as exc:
        print(f"agentdebug: not found: {exc}", file=sys.stderr)
        return 2
    except FileExistsError as exc:
        print(f"agentdebug: file already exists: {exc}", file=sys.stderr)
        print("pass --force to overwrite", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"agentdebug: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"agentdebug: {exc}", file=sys.stderr)
        return 2
    print(f"agentdebug: unknown command {args.command}", file=sys.stderr)
    return 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentdebug",
        description="Review helpers for agentic and multi-agent systems.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    report = sub.add_parser("report", help="Scaffold review reports")
    report_sub = report.add_subparsers(dest="report_command", required=True)
    init = report_sub.add_parser("init", help="Write a review report from the template")
    init.add_argument("name", help="Short title for the review")
    init.add_argument("--out", type=Path, help="Output path (default: ./<slug>.md)")
    init.add_argument("--force", action="store_true", help="Overwrite an existing file")

    lint = sub.add_parser("lint", help="Scan Python for agent-bug smells")
    lint.add_argument("path", type=Path, help="File or directory to scan")
    lint.add_argument("--format", choices=("text", "json"), default="text")

    trace = sub.add_parser("trace", help="Inspect recorded traces")
    trace_sub = trace.add_subparsers(dest="trace_command", required=True)
    summarize = trace_sub.add_parser("summarize", help="Summarize a JSONL or OTel GenAI trace")
    summarize.add_argument("file", type=Path, help="Trace file")
    summarize.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def _report_init(args: argparse.Namespace) -> int:
    destination = init_report(args.name, out=args.out, force=args.force)
    print(destination)
    return 0


def _lint(args: argparse.Namespace) -> int:
    findings = lint_path(args.path)
    if args.format == "json":
        print(format_findings_json(findings), end="")
    else:
        print(format_findings_text(findings), end="")
    return 1 if findings else 0


def _trace_summarize(args: argparse.Namespace) -> int:
    summary = summarize_path(args.file)
    if args.format == "json":
        print(json.dumps(summary.to_dict(), indent=2))
    else:
        print(format_text(summary), end="")
    return 0


def format_findings_text(findings: list[Finding]) -> str:
    if not findings:
        return "no findings\n"
    lines: list[str] = []
    for item in findings:
        lines.append(f"{item.path}:{item.line}: {item.rule_id}: {item.message}")
        lines.append(f"    hint: {item.hint}")
    return "\n".join(lines) + "\n"


def format_findings_json(findings: list[Finding]) -> str:
    payload = [item.to_dict() for item in findings]
    return json.dumps(payload, indent=2) + "\n"
