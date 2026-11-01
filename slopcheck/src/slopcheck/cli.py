"""Command-line interface for slopcheck."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from slopcheck import __version__
from slopcheck.check import check_paths, check_text
from slopcheck.load import (
    ConfigError,
    apply_em_dash_overrides,
    disable_patterns,
    disable_terms,
    load_jargon,
    load_rules,
    merge_jargon,
    merge_rules,
)
from slopcheck.model import Finding, RunResult, Summary, over_threshold
from slopcheck.suggest import SuggestError, suggest_terms
from slopcheck.text import scan_config_from


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="slopcheck",
        description=(
            "Flag AI-writing patterns and AI jargon in prose, and print a plain-language fix. "
            "Replace and cut jargon are errors. A define term warns when its first use has no "
            "definition beside it. Em dashes over the density limit are warnings."
        ),
    )
    parser.add_argument("paths", nargs="*", help="Files or directories to check. Reads stdin when omitted or when a path is -.")
    parser.add_argument("--json", action="store_true", help="Print one JSON object on stdout.")
    parser.add_argument("--rules", type=Path, help="Pattern file to merge in. Same id replaces the built-in. replace: true drops the built-ins.")
    parser.add_argument("--jargon", type=Path, help="Jargon file to merge in (YAML, or Markdown with a jargon-data block).")
    parser.add_argument("--no-jargon", action="store_true", help="Skip the jargon dictionary.")
    parser.add_argument("--config", type=Path, help="Project config. Defaults to .slopcheck.yaml in the current directory.")
    parser.add_argument("--no-config", action="store_true", help="Do not read .slopcheck.yaml.")
    parser.add_argument("--max-errors", type=int, default=None, help="Fail when errors exceed this number. Default 0. Use -1 for no error limit.")
    parser.add_argument("--max-warnings", type=int, default=None, help="Fail when warnings exceed this number. Default: no limit, unless --fail-on warning.")
    parser.add_argument("--fail-on", choices=("error", "warning", "none"), default=None, help="error (default) fails on errors only. warning also fails on any warning. none never fails on findings.")
    parser.add_argument("--exclude-category", action="append", default=[], metavar="NAME", help="Skip a category, a pattern id, or a jargon term. Repeatable.")
    parser.add_argument("--no-emdash", action="store_true", help="Do not check em-dash density.")
    parser.add_argument("--emdash-max", type=int, default=None, help="Em dashes allowed in one window. Default 2.")
    parser.add_argument("--emdash-window", type=int, default=None, help="Window size in words. Default 300.")
    parser.add_argument("--suggest-terms", action="store_true", help="Also list rare words that are not in the jargon dictionary. Needs wordfreq.")
    parser.add_argument("--zipf-below", type=float, default=None, help="With --suggest-terms, keep words under this Zipf score. Default 3.")
    parser.add_argument("--suggest-limit", type=int, default=None, help="Cap the suggestion list. Default 40.")
    parser.add_argument("--version", action="version", version=f"slopcheck {__version__}")
    return parser


def _load_config(args: argparse.Namespace) -> dict:
    if args.no_config:
        return {}
    path = args.config
    if path is None:
        for candidate in (Path.cwd() / ".slopcheck.yaml", Path.cwd() / ".slopcheck.yml"):
            if candidate.exists():
                path = candidate
                break
    if path is None:
        return {}
    if not Path(path).exists():
        raise ConfigError(f"config file missing: {path}")
    try:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: bad YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: config must be a mapping")
    return data


def _build(args: argparse.Namespace, config: dict):
    rules = load_rules()
    rules = apply_em_dash_overrides(rules, config.get("em_dash"))
    rules = disable_patterns(rules, list(config.get("disable_patterns") or []))
    rules_path = args.rules or (Path(config["rules"]) if config.get("rules") else None)
    if rules_path:
        rules = merge_rules(
            rules,
            Path(rules_path).read_text(encoding="utf-8"),
            str(rules_path),
            extra_disable=list(config.get("disable_patterns") or []),
        )
    if args.no_emdash or config.get("no_emdash"):
        rules.em_dash.enabled = False
    if args.emdash_max is not None:
        rules.em_dash.max_per_window = args.emdash_max
    if args.emdash_window is not None:
        if args.emdash_window < 1:
            raise ConfigError("--emdash-window must be at least 1")
        rules.em_dash.window_words = args.emdash_window

    skip_jargon = args.no_jargon or bool(config.get("no_jargon"))
    jargon = None
    if not skip_jargon:
        jargon = load_jargon()
        jargon = disable_terms(jargon, list(config.get("disable_terms") or []))
        jargon_path = args.jargon or (Path(config["jargon"]) if config.get("jargon") else None)
        if jargon_path:
            jargon = merge_jargon(
                jargon,
                Path(jargon_path).read_text(encoding="utf-8"),
                str(jargon_path),
                extra_disable=list(config.get("disable_terms") or []),
            )
    exclude = {item.lower() for item in (config.get("exclude_categories") or [])}
    exclude.update(item.lower() for item in args.exclude_category)
    return rules, jargon, exclude


def _limits(args: argparse.Namespace, config: dict) -> tuple[int, int, str]:
    fail_on = args.fail_on or config.get("fail_on") or "error"
    if fail_on not in ("error", "warning", "none"):
        raise ConfigError("fail_on must be error, warning, or none")
    if args.max_errors is not None:
        max_errors = args.max_errors
    elif "max_errors" in config:
        max_errors = int(config["max_errors"])
    else:
        max_errors = 0
    if args.max_warnings is not None:
        max_warnings = args.max_warnings
    elif "max_warnings" in config:
        max_warnings = int(config["max_warnings"])
    elif fail_on == "warning":
        max_warnings = 0
    else:
        max_warnings = -1
    if fail_on == "none":
        max_errors = -1
        max_warnings = -1
    return max_errors, max_warnings, fail_on


def _format_text(findings: list[Finding], summary: Summary) -> str:
    rows = []
    for finding in findings:
        friend = " (false friend)" if finding.false_friend else ""
        rows.append(
            f'{finding.path}:{finding.line}:{finding.column}: {finding.severity}: {finding.label()}: '
            f'"{finding.match}"{friend}: {finding.suggestion}'
        )
    if summary.files == 0 and not findings:
        rows.append("No files checked.")
    elif not findings:
        rows.append(f"No findings in {summary.files} file{'s' if summary.files != 1 else ''}.")
    else:
        err = f"{summary.errors} error{'s' if summary.errors != 1 else ''}"
        warn = f"{summary.warnings} warning{'s' if summary.warnings != 1 else ''}"
        files = f"{summary.files} file{'s' if summary.files != 1 else ''}"
        rows.append(f"{err}, {warn}, in {files}.")
    return "\n".join(rows) + "\n"


def _format_suggestions(items) -> str:
    if not items:
        return "No unfamiliar candidates under the Zipf cutoff.\n"
    rows = ["Unfamiliar words not in the jargon dictionary:"]
    for item in items:
        rows.append(f"  {item.term}  zipf {item.zipf:.2f}  line {item.line}  count {item.count}")
    return "\n".join(rows) + "\n"


def _read_stdin() -> str:
    return sys.stdin.read()


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 2
    try:
        config = _load_config(args)
        rules, jargon, exclude = _build(args, config)
        scan = scan_config_from(config)
        max_errors, max_warnings, _fail_on = _limits(args, config)
    except ConfigError as exc:
        print(f"slopcheck: {exc}", file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(f"slopcheck: file not found: {exc}", file=sys.stderr)
        return 2

    paths = list(args.paths)
    if not paths:
        if sys.stdin.isatty():
            print("Give a file, a directory, or pipe text on stdin.", file=sys.stderr)
            return 2
        paths = ["-"]

    findings: list[Finding] = []
    notes: list[str] = []
    file_count = 0
    stdin_text = None
    try:
        file_paths = [Path(item) for item in paths if item != "-"]
        if file_paths:
            found, file_count, notes = check_paths(file_paths, rules, jargon, exclude, scan)
            findings.extend(found)
        if "-" in paths or (len(paths) == 1 and paths[0] == "-"):
            stdin_text = _read_stdin()
            file_count += 1
            findings.extend(check_text(stdin_text, "<stdin>", rules, jargon, exclude, scan))
    except ConfigError as exc:
        print(f"slopcheck: {exc}", file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(f"slopcheck: file not found: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"slopcheck: {exc}", file=sys.stderr)
        return 2

    for note in notes:
        print(f"slopcheck: {note}", file=sys.stderr)

    summary = Summary(files=file_count)
    summary.add(findings)
    suggestions = None
    if args.suggest_terms:
        if jargon is None:
            print("slopcheck: --suggest-terms needs the jargon dictionary. Drop --no-jargon.", file=sys.stderr)
            return 2
        zipf_below = args.zipf_below if args.zipf_below is not None else float(config.get("zipf_below", 3.0))
        limit = args.suggest_limit if args.suggest_limit is not None else int(config.get("suggest_limit", 40))
        blobs: list[tuple[str, str]] = []
        try:
            for item in paths:
                if item == "-":
                    blobs.append(("<stdin>", stdin_text or ""))
                else:
                    path = Path(item)
                    from slopcheck.check import iter_prose_files, read_document
                    for file in iter_prose_files(path):
                        text = read_document(file)
                        if text is not None:
                            blobs.append((str(file), text))
            combined_suggestions = []
            for label, text in blobs:
                for item in suggest_terms(text, jargon, zipf_below=zipf_below, limit=limit, scan=scan):
                    combined_suggestions.append(item)
            combined_suggestions.sort(key=lambda item: (item.zipf, item.term))
            suggestions = combined_suggestions[:limit]
        except SuggestError as exc:
            print(f"slopcheck: {exc}", file=sys.stderr)
            return 2

    result = RunResult(findings=findings, summary=summary, suggestions=suggestions)
    failed = over_threshold(summary, max_errors, max_warnings)
    if args.json:
        payload = {
            "findings": [item.to_dict() for item in result.findings],
            "summary": summary.to_dict(),
            "ok": not failed,
        }
        if suggestions is not None:
            payload["suggestions"] = [item.to_dict() for item in suggestions]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        sys.stdout.write(_format_text(findings, summary))
        if suggestions is not None:
            sys.stdout.write(_format_suggestions(suggestions))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
