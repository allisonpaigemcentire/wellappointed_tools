"""Flag sentences that copy a brief, outline, or prompt too closely.

The check runs only when a brief is passed. A line in the brief marked
`<!-- slopcheck-quote -->`, or a block between `<!-- slopcheck-quotes -->`
and `<!-- /slopcheck-quotes -->`, is an intended quote and is not a leak.
"""

from __future__ import annotations

import re

from slopcheck.model import Finding, finding_at
from slopcheck.options import BriefConfig
from slopcheck.text import (
    HEADING_RE,
    LineInfo,
    ScanConfig,
    Sentence,
    body_sentences,
    line_suppressed,
    split_sentences,
)
from slopcheck.tokens import content_words

_INLINE = re.compile(r"<!--\s*slopcheck-quote\s*-->", re.IGNORECASE)
_ON = re.compile(r"<!--\s*slopcheck-quotes\s*-->", re.IGNORECASE)
_OFF = re.compile(r"<!--\s*/slopcheck-quotes\s*-->", re.IGNORECASE)
_LIST = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_HEAD = re.compile(r"^\s*#{1,6}\s+")


def parse_brief(text: str) -> tuple[list[str], list[str]]:
    """Return `(source sentences, allowlisted sentences)`."""
    source: list[str] = []
    allow: list[str] = []
    bucket = source
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if _ON.search(line):
            bucket = allow
            continue
        if _OFF.search(line):
            bucket = source
            continue
        if _INLINE.search(line):
            allow.append(_INLINE.sub(" ", line))
            continue
        bucket.append(line)
    return _sentences("\n".join(source)), _sentences("\n".join(allow))


def _sentences(text: str) -> list[str]:
    kept: list[str] = []
    for raw in text.split("\n"):
        line = _HEAD.sub("", raw)
        line = _LIST.sub("", line).strip()
        if not line or line == "---":
            continue
        kept.append(line)
    joined = " ".join(kept)
    sentences: list[str] = []
    for start, end in split_sentences(joined):
        core = joined[start:end].strip()
        if core:
            sentences.append(core)
    if not sentences and joined.strip():
        sentences.append(joined.strip())
    return sentences


def _overlap(left: list[str], right: list[str]) -> float:
    if not left or not right:
        return 0.0
    shared = len(set(left) & set(right))
    return shared / min(len(left), len(right))


def _ngrams(words: list[str], size: int) -> set[tuple[str, ...]]:
    if len(words) < size:
        return set()
    return {tuple(words[index:index + size]) for index in range(0, len(words) - size + 1)}


def _too_close(output: list[str], source: list[str], config: BriefConfig) -> tuple[bool, float, str]:
    score = _overlap(output, source)
    shared = _ngrams(output, config.ngram) & _ngrams(source, config.ngram)
    phrase = " ".join(next(iter(shared))) if shared else ""
    by_overlap = len(output) >= config.min_content_words and score >= config.overlap
    by_ngram = bool(shared)
    return (by_overlap or by_ngram), score, phrase


def _output_sentences(lines: list[LineInfo], scan: ScanConfig | None) -> list[Sentence]:
    sentences: list[Sentence] = []
    for sentence in body_sentences(lines, scan):
        if HEADING_RE.match(sentence.text) or sentence.text.lstrip().startswith("|"):
            continue
        sentences.append(sentence)
    return sentences


def brief_findings(
    lines: list[LineInfo],
    path: str,
    briefs: list[str],
    config: BriefConfig,
    scan: ScanConfig | None = None,
) -> list[Finding]:
    if not config.enabled or not briefs:
        return []
    sources: list[str] = []
    allowed: list[str] = []
    for brief in briefs:
        source, allow = parse_brief(brief)
        sources.extend(source)
        allowed.extend(allow)
    if not sources and not allowed:
        return []
    source_words = [(sentence, content_words(sentence)) for sentence in sources]
    allow_words = [(sentence, content_words(sentence)) for sentence in allowed]
    findings: list[Finding] = []
    for sentence in _output_sentences(lines, scan):
        if line_suppressed(lines, sentence.line, rule_id="brief-leak", category="brief-leak"):
            continue
        output = content_words(sentence.text)
        if len(output) < config.ngram and len(output) < config.min_content_words:
            continue
        if any(_too_close(output, words, config)[0] for _text, words in allow_words):
            continue
        best_score = 0.0
        best_phrase = ""
        best_source = ""
        hit = False
        for source, words in source_words:
            close, score, phrase = _too_close(output, words, config)
            if not close:
                continue
            hit = True
            if score >= best_score:
                best_score = score
                best_phrase = phrase
                best_source = source
        if not hit:
            continue
        snippet = re.sub(r"\s+", " ", sentence.text).strip()
        if len(snippet) > 80:
            snippet = snippet[:77].rstrip() + "..."
        source_bit = re.sub(r"\s+", " ", best_source).strip()
        if len(source_bit) > 70:
            source_bit = source_bit[:67].rstrip() + "..."
        detail = f"Token overlap {best_score:.2f} with the brief ({source_bit!r})."
        if best_phrase:
            detail = f'Shared wording "{best_phrase}". {detail}'
        start = 0
        end = len(sentence.masked) if sentence.masked else len(snippet)
        findings.append(finding_at(
            path, sentence.origins, start, max(end, 1), sentence.line,
            severity=config.severity,
            category="brief-leak",
            rule_id="brief-leak",
            match=snippet,
            suggestion=(
                f"{detail} Rewrite it, or mark that brief line as an intended quote "
                "with <!-- slopcheck-quote -->."
            ),
        ))
    return findings
