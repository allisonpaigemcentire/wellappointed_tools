"""Measure false flags on clean prose and recall on labeled problems.

The shipped labeled files are synthetic. Recall on them overstates how the
checker behaves on a real draft. Point --clean at a local folder to measure
your own prose. That folder is not copied into the repository.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field, replace
from pathlib import Path

import yaml

from slopcheck.check import check_text, iter_prose_files, read_document
from slopcheck.load import ConfigError, load_jargon, load_rules
from slopcheck.options import CheckOptions, default_options
from slopcheck.text import ScanConfig, classify_lines, default_scan_config, mask_text
from slopcheck.tokens import TOKEN_RE

_NOTE = (
    "The labeled files plant problems on purpose. "
    "Recall on them overstates accuracy on real drafts."
)


@dataclass
class BenchReport:
    clean_files: int = 0
    clean_words: int = 0
    clean_findings: int = 0
    false_flags_per_1000: float = 0.0
    by_category: dict[str, int] = field(default_factory=dict)
    by_rule: dict[str, int] = field(default_factory=dict)
    labeled_cases: int = 0
    labeled_expected: int = 0
    labeled_hit: int = 0
    recall: float | None = None
    quiet_violations: int = 0
    notes: list[str] = field(default_factory=list)

    def summary_sentence(self) -> str:
        rate = f"{self.false_flags_per_1000:.2f}"
        files = f"{self.clean_files} file" if self.clean_files == 1 else f"{self.clean_files} files"
        findings = (
            f"{self.clean_findings} finding"
            if self.clean_findings == 1
            else f"{self.clean_findings} findings"
        )
        if self.labeled_expected:
            recall = f"{self.recall:.2f}" if self.recall is not None else "n/a"
            return (
                f"Clean corpus: {files}, {self.clean_words} words, "
                f"{findings}, {rate} false flags per 1,000 words. "
                f"Labeled corpus: {self.labeled_hit} of {self.labeled_expected} planted hits, "
                f"recall {recall}."
            )
        return (
            f"Clean corpus: {files}, {self.clean_words} words, "
            f"{findings}, {rate} false flags per 1,000 words."
        )

    def to_dict(self) -> dict:
        return {
            "clean_files": self.clean_files,
            "clean_words": self.clean_words,
            "clean_findings": self.clean_findings,
            "false_flags_per_1000": round(self.false_flags_per_1000, 2),
            "by_category": self.by_category,
            "by_rule": self.by_rule,
            "labeled_cases": self.labeled_cases,
            "labeled_expected": self.labeled_expected,
            "labeled_hit": self.labeled_hit,
            "recall": None if self.recall is None else round(self.recall, 2),
            "quiet_violations": self.quiet_violations,
            "notes": self.notes,
        }


def shipped_bench_dir() -> Path:
    candidate = Path(__file__).resolve().parents[2] / "bench"
    if (candidate / "clean").is_dir() and (candidate / "labeled").is_dir():
        return candidate
    raise ConfigError(
        "The shipped bench corpus is not next to this install. "
        "Pass --clean and --labeled, or run slopcheck bench from a checkout."
    )


def count_words(text: str, scan: ScanConfig | None = None) -> int:
    """Words in the lines the checker can see. Code, skips, and comments drop out."""
    total = 0
    for line in classify_lines(text, scan):
        if line.kind in {"code", "skip", "front"}:
            continue
        source = line.title_value if line.kind == "title" and line.title_value is not None else line.text
        visible = mask_text(source, scan, quotes=False)
        total += len(TOKEN_RE.findall(visible))
    return total


def _options_for(case: dict, base: CheckOptions) -> CheckOptions:
    damage = base.damage
    if case.get("missing_function_word"):
        damage = replace(damage, missing_function_word=True)
    return replace(base, damage=damage)


def _expect_list(raw: object) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list) or not all(isinstance(item, str) and item.strip() for item in raw):
        raise ConfigError("expect must be a list of rule ids")
    return [item.strip() for item in raw]


def _score_expected(findings, expected: list[str]) -> int:
    pool = [item.rule_id for item in findings]
    hits = 0
    for rule in expected:
        if rule in pool:
            pool.remove(rule)
            hits += 1
    return hits


def run_bench(
    clean_dir: Path | None = None,
    labeled_dir: Path | None = None,
    *,
    options: CheckOptions | None = None,
    scan: ScanConfig | None = None,
) -> BenchReport:
    """Measure one clean folder and, when present, one labeled folder."""
    opts = options or default_options()
    scan = scan or default_scan_config()
    rules = load_rules()
    jargon = load_jargon()
    report = BenchReport(notes=[_NOTE])
    if clean_dir is not None:
        _measure_clean(clean_dir, report, rules, jargon, opts, scan)
    if labeled_dir is not None:
        _measure_labeled(labeled_dir, report, rules, jargon, opts, scan)
    if report.clean_words:
        report.false_flags_per_1000 = report.clean_findings * 1000 / report.clean_words
    if report.labeled_expected:
        report.recall = report.labeled_hit / report.labeled_expected
    return report


def _measure_clean(folder: Path, report: BenchReport, rules, jargon, options, scan) -> None:
    if not folder.is_dir():
        raise ConfigError(f"clean folder not found: {folder}")
    files = iter_prose_files(folder)
    categories: Counter[str] = Counter()
    rules_hit: Counter[str] = Counter()
    for file in files:
        text = read_document(file)
        if text is None:
            continue
        report.clean_files += 1
        report.clean_words += count_words(text, scan)
        for finding in check_text(text, str(file), rules, jargon, scan=scan, options=options):
            report.clean_findings += 1
            categories[finding.category] += 1
            rules_hit[finding.rule_id] += 1
    report.by_category = dict(categories)
    report.by_rule = dict(rules_hit)


def _measure_labeled(folder: Path, report: BenchReport, rules, jargon, options, scan) -> None:
    if not folder.is_dir():
        raise ConfigError(f"labeled folder not found: {folder}")
    manifest_path = folder / "manifest.yaml"
    if not manifest_path.exists():
        raise ConfigError(f"{folder} has no manifest.yaml")
    try:
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"{manifest_path}: bad YAML: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ConfigError(f"{manifest_path}: the manifest must be a mapping")
    cases = manifest.get("cases") or []
    if not isinstance(cases, list):
        raise ConfigError(f"{manifest_path}: cases must be a list")
    for index, case in enumerate(cases, 1):
        if not isinstance(case, dict) or not case.get("file"):
            raise ConfigError(f"{manifest_path}: case {index} needs a file")
        path = folder / str(case["file"])
        if not path.exists():
            raise ConfigError(f"labeled file missing: {path}")
        text = path.read_text(encoding="utf-8")
        briefs: list[str] = []
        for brief in case.get("briefs") or []:
            brief_path = folder / str(brief)
            if not brief_path.exists():
                raise ConfigError(f"brief missing: {brief_path}")
            briefs.append(brief_path.read_text(encoding="utf-8"))
        findings = check_text(
            text,
            str(path),
            rules,
            jargon,
            scan=scan,
            options=_options_for(case, options),
            briefs=briefs or None,
        )
        expected = _expect_list(case.get("expect"))
        report.labeled_cases += 1
        report.labeled_expected += len(expected)
        report.labeled_hit += _score_expected(findings, expected)
        for quiet in case.get("quiet") or []:
            if not isinstance(quiet, dict) or "line" not in quiet or "rule" not in quiet:
                raise ConfigError(f"{manifest_path}: quiet entries need line and rule")
            line = int(quiet["line"])
            rule = str(quiet["rule"])
            if any(item.line == line and item.rule_id == rule for item in findings):
                report.quiet_violations += 1


def format_report(report: BenchReport) -> str:
    rows = [report.summary_sentence()]
    if report.by_category:
        rows.append("Findings on the clean corpus, by category:")
        for category, count in sorted(report.by_category.items()):
            rows.append(f"  {category}: {count}")
    if report.by_rule:
        rows.append("Findings on the clean corpus, by rule:")
        for rule, count in sorted(report.by_rule.items()):
            rows.append(f"  {rule}: {count}")
    if report.quiet_violations:
        rows.append(f"Allowlist slips: {report.quiet_violations}.")
    for note in report.notes:
        rows.append(note)
    return "\n".join(rows) + "\n"


def bench_main(argv: list[str] | None = None) -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        prog="slopcheck bench",
        description=(
            "Count false flags per 1,000 words on clean prose, and recall on labeled problems. "
            "The shipped labeled set is synthetic and overstates accuracy."
        ),
    )
    parser.add_argument("--clean", type=Path, help="Folder of clean prose. Defaults to the shipped public-domain excerpts.")
    parser.add_argument("--labeled", type=Path, help="Folder with manifest.yaml. Defaults to the shipped synthetic set.")
    parser.add_argument("--json", action="store_true", help="Print the report as JSON.")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 2
    clean = args.clean
    labeled = args.labeled
    if clean is None and labeled is None:
        try:
            shipped = shipped_bench_dir()
        except ConfigError as exc:
            print(f"slopcheck: {exc}", file=sys.stderr)
            return 2
        clean = shipped / "clean"
        labeled = shipped / "labeled"
    try:
        report = run_bench(clean, labeled)
    except (ConfigError, OSError) as exc:
        print(f"slopcheck: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        sys.stdout.write(format_report(report))
    return 0
