"""Sentence-length rhythm. Warnings fire only past a threshold.

The numbers are always available from `measure_rhythm`. A short document stays
quiet: the flat-rhythm and long-sentence warnings wait for `min_sentences`.
Dialogue share is reported when the text has quoted speech. It is not itself
a warning.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from slopcheck.model import Finding
from slopcheck.options import RhythmConfig
from slopcheck.text import (
    QUOTE_RE,
    LineInfo,
    ScanConfig,
    Sentence,
    line_suppressed,
    prose_paragraphs,
    prose_sentences,
)
from slopcheck.tokens import TOKEN_RE


@dataclass
class RhythmMetrics:
    sentences: int
    mean: float
    stdev: float
    cv: float
    long_words: int
    long_count: int
    long_share: float
    longest_similar_run: int
    run_line: int | None
    dialogue_share: float

    def to_dict(self) -> dict:
        data = {
            "sentences": self.sentences,
            "mean": round(self.mean, 2),
            "stdev": round(self.stdev, 2),
            "cv": round(self.cv, 2),
            "long_words": self.long_words,
            "long_count": self.long_count,
            "long_share": round(self.long_share, 3),
            "longest_similar_run": self.longest_similar_run,
            "dialogue_share": round(self.dialogue_share, 3),
        }
        if self.dialogue_share <= 0:
            data["dialogue_share"] = 0
        return data


def _lengths(sentences: list[Sentence]) -> list[tuple[Sentence, int]]:
    measured: list[tuple[Sentence, int]] = []
    for sentence in sentences:
        count = len(TOKEN_RE.findall(sentence.text))
        if count:
            measured.append((sentence, count))
    return measured


def _dialogue_share(lines: list[LineInfo]) -> float:
    words = 0
    quoted = 0
    for group in prose_paragraphs(lines):
        text = " ".join(line.text for line in group)
        words += len(TOKEN_RE.findall(text))
        for match in QUOTE_RE.finditer(text):
            quoted += len(TOKEN_RE.findall(match.group(0)))
    if words == 0:
        return 0.0
    return quoted / words


def _longest_run(measured: list[tuple[Sentence, int]], config: RhythmConfig) -> tuple[int, int | None]:
    best = 1 if measured else 0
    best_line = measured[0][0].line if measured else None
    start = 0
    for index in range(len(measured)):
        if index == 0:
            continue
        window = [length for _sentence, length in measured[start:index + 1]]
        tall_enough = all(length >= config.run_min_words for length in window)
        if tall_enough and max(window) - min(window) <= config.run_span:
            if len(window) > best:
                best = len(window)
                best_line = measured[start][0].line
            continue
        start = index
    return best, best_line


def measure_rhythm(
    lines: list[LineInfo],
    config: RhythmConfig | None = None,
    scan: ScanConfig | None = None,
) -> RhythmMetrics | None:
    config = config or RhythmConfig()
    measured = _lengths(prose_sentences(lines, scan))
    if not measured:
        return None
    lengths = [length for _sentence, length in measured]
    mean = statistics.fmean(lengths)
    stdev = statistics.pstdev(lengths) if len(lengths) > 1 else 0.0
    cv = (stdev / mean) if mean else 0.0
    long_count = sum(1 for length in lengths if length >= config.long_words)
    run, run_line = _longest_run(measured, config)
    return RhythmMetrics(
        sentences=len(lengths),
        mean=mean,
        stdev=stdev,
        cv=cv,
        long_words=config.long_words,
        long_count=long_count,
        long_share=long_count / len(lengths),
        longest_similar_run=run,
        run_line=run_line,
        dialogue_share=_dialogue_share(lines),
    )


def _summary(metrics: RhythmMetrics) -> str:
    text = (
        f"Mean {metrics.mean:.1f} words, standard deviation {metrics.stdev:.1f}, "
        f"coefficient of variation {metrics.cv:.2f}. "
        f"Sentences at {metrics.long_words}+ words: {metrics.long_share:.0%} "
        f"({metrics.long_count} of {metrics.sentences})."
    )
    if metrics.dialogue_share > 0:
        text += f" Dialogue share: {metrics.dialogue_share:.0%}."
    return text


def rhythm_findings(
    lines: list[LineInfo],
    path: str,
    config: RhythmConfig,
    scan: ScanConfig | None = None,
) -> list[Finding]:
    if not config.enabled:
        return []
    metrics = measure_rhythm(lines, config, scan)
    if metrics is None or metrics.sentences < config.min_sentences:
        return []
    anchor = prose_sentences(lines, scan)
    line = anchor[0].line if anchor else 1
    column = anchor[0].origins[0][1] if anchor and anchor[0].origins else 1
    findings: list[Finding] = []
    summary = _summary(metrics)

    def add(rule_id: str, match: str, detail: str) -> None:
        if line_suppressed(lines, line, rule_id=rule_id, category="rhythm"):
            return
        findings.append(Finding(
            path=path,
            line=line,
            column=column,
            end_line=line,
            end_column=column + len(match),
            severity=config.severity,
            category="rhythm",
            rule_id=rule_id,
            match=match,
            suggestion=f"{detail} {summary}",
        ))

    if config.flag_flat and metrics.cv < config.cv_below:
        add(
            "rhythm-flat",
            f"cv {metrics.cv:.2f}",
            "Flat rhythm: sentence length barely changes.",
        )
    if config.flag_long and metrics.long_share >= config.long_share:
        add(
            "rhythm-long",
            f"{metrics.long_share:.0%} at {metrics.long_words}+ words",
            "Too many long sentences.",
        )
    if config.flag_run and metrics.longest_similar_run >= config.run_length:
        where = f" starting at line {metrics.run_line}" if metrics.run_line else ""
        add(
            "rhythm-run",
            f"{metrics.longest_similar_run} similar sentences",
            f"A run of {metrics.longest_similar_run} sentences of similar length{where}.",
        )
    return findings
