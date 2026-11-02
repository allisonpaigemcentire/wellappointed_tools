"""Command-line interface for slopcheck."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from slopcheck import __version__
from slopcheck.baseline import compare_findings
from slopcheck.check import check_paths, check_text, iter_prose_files, read_document
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
from slopcheck.options import brief_paths_from, options_from_config
from slopcheck.suggest import SuggestError, suggest_terms
from slopcheck.text import classify_lines, scan_config_from


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="slopcheck",
        description=(
            "Flag AI-writing patterns and AI jargon in prose, and print a plain-language fix. "
            "Replace and cut jargon are errors. A define term warns when its first use has no "
            "definition beside it. Em dashes over the density limit are warnings. "
            "Repeated phrases, flat rhythm, and edit damage are warnings. "
            "Pass a brief to flag sentences that copy it. "
            "`slopcheck diff OLD NEW` reports findings the edit introduced and findings it fixed. "
            "`slopcheck bench` measures false flags on clean prose and recall on labeled problems."
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
    parser.add_argument("--brief", action="append", default=[], type=Path, metavar="PATH", help="Brief, outline, or prompt. Repeatable. Sentences that copy it are warnings.")
    parser.add_argument("--baseline", type=Path, help="Report only findings that are new relative to this file or directory, and list findings the edit fixed.")
    parser.add_argument("--no-repetition", action="store_true", help="Skip repeated phrases and near-duplicate sentences.")
    parser.add_argument("--no-rhythm", action="store_true", help="Skip sentence-rhythm warnings.")
    parser.add_argument("--no-edit-damage", action="store_true", help="Skip doubled words, lowercase starts, and dangling punctuation.")
    parser.add_argument("--function-words", action="store_true", help="Opt in to the missing-function-word check. Off by default.")
    parser.add_argument("--show-rhythm", action="store_true", help="Print rhythm numbers even when they stay under the warning thresholds.")
    parser.add_argument("--repetition-more-than", type=int, default=None, metavar="N", help="Flag a content phrase repeated more than N times. Default 2.")
    parser.add_argument("--long-sentence-words", type=int, default=None, metavar="N", help="A long sentence is N words or more. Default 25.")
    parser.add_argument("--brief-overlap", type=float, default=None, metavar="FRACTION", help="Brief-leak token overlap. Default 0.72.")
    parser.add_argument("--known-name", action="append", default=[], metavar="NAME", help="A name that counts even at the start of a sentence. Repeatable.")
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


def _options(args: argparse.Namespace, config: dict):
    opts = options_from_config(config)
    if args.no_repetition or config.get("no_repetition"):
        opts.repetition.enabled = False
    if args.no_rhythm or config.get("no_rhythm"):
        opts.rhythm.enabled = False
    if args.no_edit_damage or config.get("no_edit_damage"):
        opts.damage.enabled = False
    if args.function_words or config.get("function_words"):
        opts.damage.missing_function_word = True
    if args.repetition_more_than is not None:
        if args.repetition_more_than < 1:
            raise ConfigError("--repetition-more-than must be at least 1")
        opts.repetition.more_than = args.repetition_more_than
    if args.long_sentence_words is not None:
        if args.long_sentence_words < 8:
            raise ConfigError("--long-sentence-words must be at least 8")
        opts.rhythm.long_words = args.long_sentence_words
    if args.brief_overlap is not None:
        if not 0 <= args.brief_overlap <= 1:
            raise ConfigError("--brief-overlap must be from 0 to 1")
        opts.brief.overlap = args.brief_overlap
    if args.show_rhythm:
        opts.show_rhythm = True
    for name in args.known_name:
        opts.known_names.add(name.casefold())
    return opts


def _brief_texts(args: argparse.Namespace, config: dict) -> list[str]:
    paths = [Path(item) for item in brief_paths_from(config)]
    paths.extend(args.brief or [])
    texts: list[str] = []
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(str(path))
        texts.append(path.read_text(encoding="utf-8"))
    return texts


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


def _format_text(
    findings: list[Finding],
    summary: Summary,
    fixed: list[Finding] | None = None,
    *,
    baseline: bool = False,
) -> str:
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
        noun = "new findings" if baseline else "findings"
        rows.append(f"No {noun} in {summary.files} file{'s' if summary.files != 1 else ''}.")
    else:
        err = f"{summary.errors} error{'s' if summary.errors != 1 else ''}"
        warn = f"{summary.warnings} warning{'s' if summary.warnings != 1 else ''}"
        files = f"{summary.files} file{'s' if summary.files != 1 else ''}"
        rows.append(f"{err}, {warn}, in {files}.")
    if fixed:
        for finding in fixed:
            rows.append(
                f'{finding.path}:{finding.line}:{finding.column}: fixed: {finding.label()}: '
                f'"{finding.match}": {finding.suggestion}'
            )
        noun = "finding" if len(fixed) == 1 else "findings"
        rows.append(f"Fixed {len(fixed)} {noun} from the baseline.")
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


def _baseline_path(args: argparse.Namespace, config: dict) -> Path | None:
    if getattr(args, "baseline", None):
        return Path(args.baseline)
    if config.get("baseline"):
        return Path(str(config["baseline"]))
    return None


def _relative_files(path: Path) -> list[tuple[str, Path]]:
    if path.is_file():
        return [(path.name, path)]
    return [(str(file.relative_to(path)), file) for file in iter_prose_files(path)]


def _pairs(baseline: Path, inputs: list[Path]) -> list[tuple[Path | None, Path | None]]:
    """Pair baseline files with edited files by relative path."""
    if not baseline.exists():
        raise FileNotFoundError(str(baseline))
    if baseline.is_file():
        edited: list[Path] = []
        for item in inputs:
            if not item.exists():
                raise FileNotFoundError(str(item))
            edited.extend(iter_prose_files(item) if item.is_dir() else [item])
        if len(edited) != 1:
            raise ConfigError("a baseline file needs one file to compare")
        return [(baseline, edited[0])]
    old_map = {rel: file for rel, file in _relative_files(baseline)}
    pairs: list[tuple[Path | None, Path | None]] = []
    seen: set[str] = set()
    for item in inputs:
        if not item.exists():
            raise FileNotFoundError(str(item))
        for rel, file in _relative_files(item):
            seen.add(rel)
            pairs.append((old_map.get(rel), file))
    for rel, file in old_map.items():
        if rel not in seen:
            pairs.append((file, None))
    return pairs


def _rhythm_line(row: dict) -> str:
    dialogue = ""
    if row.get("dialogue_share"):
        dialogue = f", dialogue {row['dialogue_share']:.0%}"
    return (
        f"{row['path']}: rhythm: {row['sentences']} sentences, "
        f"mean {row['mean']:.1f}, sd {row['stdev']:.1f}, cv {row['cv']:.2f}, "
        f"long({row['long_words']}+) {row['long_share']:.0%}{dialogue}"
    )


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    if raw and raw[0] == "bench":
        from slopcheck.bench import bench_main
        return bench_main(raw[1:])
    diff_mode = bool(raw and raw[0] == "diff")
    if diff_mode:
        raw = raw[1:]
    parser = _parser()
    try:
        args = parser.parse_args(raw)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 2
    if diff_mode:
        file_args = [item for item in args.paths if item != "-"]
        if len(file_args) != 2 or "-" in args.paths:
            print("usage: slopcheck diff OLD NEW", file=sys.stderr)
            return 2
        args.baseline = Path(file_args[0])
        args.paths = [file_args[1]]
    try:
        config = _load_config(args)
        rules, jargon, exclude = _build(args, config)
        scan = scan_config_from(config)
        options = _options(args, config)
        briefs = _brief_texts(args, config)
        max_errors, max_warnings, _fail_on = _limits(args, config)
        baseline = _baseline_path(args, config)
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
    fixed: list[Finding] | None = None
    notes: list[str] = []
    file_count = 0
    stdin_text = None
    blobs: list[tuple[str, str]] = []
    try:
        file_paths = [Path(item) for item in paths if item != "-"]
        if baseline is not None and file_paths:
            introduced, fixed_items, file_count, notes = _check_against_baseline(
                baseline, file_paths, rules, jargon, exclude, scan, options, briefs,
            )
            findings.extend(introduced)
            fixed = fixed_items
        elif file_paths:
            found, file_count, notes = check_paths(
                file_paths, rules, jargon, exclude, scan, options, briefs,
            )
            findings.extend(found)
        if "-" in paths:
            stdin_text = _read_stdin()
            file_count += 1
            blobs.append(("<stdin>", stdin_text))
            new_findings = check_text(stdin_text, "<stdin>", rules, jargon, exclude, scan, options, briefs)
            if baseline is not None and baseline.is_file():
                old_text = read_document(baseline)
                if old_text is None:
                    raise ConfigError(f"baseline looks binary: {baseline}")
                old_findings = check_text(
                    old_text, str(baseline), rules, jargon, exclude, scan, options, briefs,
                )
                introduced, fixed_items = compare_findings(old_findings, new_findings)
                findings.extend(introduced)
                fixed = (fixed or []) + fixed_items
            elif baseline is not None:
                raise ConfigError("a piped check needs a baseline file, not a directory")
            else:
                findings.extend(new_findings)
        if file_paths:
            for item in file_paths:
                for file in iter_prose_files(item):
                    text = read_document(file)
                    if text is not None:
                        blobs.append((str(file), text))
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
        try:
            if not blobs:
                for item in paths:
                    if item == "-":
                        blobs.append(("<stdin>", stdin_text or ""))
                    else:
                        path = Path(item)
                        for file in iter_prose_files(path):
                            text = read_document(file)
                            if text is not None:
                                blobs.append((str(file), text))
            combined_suggestions = []
            for label, text in blobs:
                combined_suggestions.extend(suggest_terms(
                    text, jargon, zipf_below=zipf_below, limit=limit, scan=scan,
                    known_names=options.known_names,
                ))
            combined_suggestions.sort(key=lambda item: (item.zipf, item.term))
            suggestions = combined_suggestions[:limit]
        except SuggestError as exc:
            print(f"slopcheck: {exc}", file=sys.stderr)
            return 2

    result = RunResult(findings=findings, summary=summary, suggestions=suggestions)
    failed = over_threshold(summary, max_errors, max_warnings)
    rhythm_rows = _rhythm_rows(blobs, scan, options)
    if args.json:
        payload = {
            "findings": [item.to_dict() for item in result.findings],
            "summary": summary.to_dict(),
            "ok": not failed,
        }
        if fixed is not None:
            payload["fixed"] = [item.to_dict() for item in fixed]
            payload["summary"]["fixed"] = len(fixed)
        if rhythm_rows:
            payload["rhythm"] = rhythm_rows
        if suggestions is not None:
            payload["suggestions"] = [item.to_dict() for item in suggestions]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        sys.stdout.write(_format_text(findings, summary, fixed, baseline=baseline is not None))
        if options.show_rhythm:
            for row in rhythm_rows:
                sys.stdout.write(_rhythm_line(row) + "\n")
        if suggestions is not None:
            sys.stdout.write(_format_suggestions(suggestions))
    return 1 if failed else 0


def _check_against_baseline(
    baseline: Path,
    inputs: list[Path],
    rules,
    jargon,
    exclude,
    scan,
    options,
    briefs,
) -> tuple[list[Finding], list[Finding], int, list[str]]:
    introduced: list[Finding] = []
    fixed: list[Finding] = []
    notes: list[str] = []
    count = 0
    for old, new in _pairs(baseline, inputs):
        old_findings: list[Finding] = []
        new_findings: list[Finding] = []
        if old is not None:
            old_text = read_document(old)
            if old_text is None:
                notes.append(f"skipped binary file {old}")
            else:
                old_findings = check_text(old_text, str(old), rules, jargon, exclude, scan, options, briefs)
        if new is not None:
            new_text = read_document(new)
            if new_text is None:
                notes.append(f"skipped binary file {new}")
                continue
            count += 1
            new_findings = check_text(new_text, str(new), rules, jargon, exclude, scan, options, briefs)
        added, gone = compare_findings(old_findings, new_findings)
        introduced.extend(added)
        fixed.extend(gone)
    introduced.sort(key=lambda item: (item.path, item.line, item.column, item.rule_id))
    fixed.sort(key=lambda item: (item.path, item.line, item.column, item.rule_id))
    return introduced, fixed, count, notes


def _rhythm_rows(blobs: list[tuple[str, str]], scan, options) -> list[dict]:
    from slopcheck.rhythm import measure_rhythm

    if not options.rhythm.enabled:
        return []
    rows: list[dict] = []
    for label, text in blobs:
        metrics = measure_rhythm(classify_lines(text, scan), options.rhythm, scan)
        if metrics is None:
            continue
        rows.append({"path": label, **metrics.to_dict()})
    return rows


if __name__ == "__main__":
    sys.exit(main())
