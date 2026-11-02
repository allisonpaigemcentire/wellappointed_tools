"""Repeated phrases and near-duplicate sentences inside one document.

Content n-grams ignore function words, so "of the" does not count. Quoted
spans are masked before the n-gram pass. Near-duplicates keep the quotes,
because a speech said twice is the case they exist for. Headings, lists, and
tables are left out of both.
"""

from __future__ import annotations

import re
from collections import defaultdict
from difflib import SequenceMatcher

from slopcheck.model import Finding, finding_at
from slopcheck.options import RepetitionConfig
from slopcheck.text import (
    LineInfo,
    ScanConfig,
    Sentence,
    any_line_suppressed,
    prose_sentences,
)
from slopcheck.tokens import TOKEN_RE, is_content_word, norm_token

_CLEAN = re.compile(r"[^a-z0-9'\s]+")


def _normalize(text: str) -> list[str]:
    flat = text.casefold().replace("’", "'")
    flat = _CLEAN.sub(" ", flat)
    return [token for token in flat.split() if token]


def _surface(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def repetition_findings(
    lines: list[LineInfo],
    path: str,
    config: RepetitionConfig,
    scan: ScanConfig | None = None,
) -> list[Finding]:
    if not config.enabled:
        return []
    sentences = prose_sentences(lines, scan)
    findings = _phrase_findings(sentences, lines, path, config)
    if config.near_duplicate:
        findings.extend(_near_findings(sentences, lines, path, config))
    return findings


def _phrase_findings(
    sentences: list[Sentence],
    lines: list[LineInfo],
    path: str,
    config: RepetitionConfig,
) -> list[Finding]:
    # key -> list of (sentence index, surface, origin start, origin end, line numbers)
    groups: dict[tuple[str, ...], list[tuple[int, str, int, int, set[int]]]] = defaultdict(list)
    for index, sentence in enumerate(sentences):
        occurrences = _ngrams(sentence, config.min_ngram, config.max_ngram)
        for key, surface, start, end, numbers in occurrences:
            groups[key].append((index, surface, start, end, numbers))
    # Longer phrases win. A shorter one drops when a longer one already covers it.
    ranked = sorted(groups, key=lambda key: (-len(key), -len(groups[key]), key))
    covered: dict[int, list[tuple[int, int]]] = defaultdict(list)
    findings: list[Finding] = []
    for key in ranked:
        hits = groups[key]
        if len(hits) <= config.more_than:
            continue
        fresh = []
        for hit in hits:
            index, _surface, start, end, _numbers = hit
            if any(span_start <= start and end <= span_end for span_start, span_end in covered[index]):
                continue
            fresh.append(hit)
        if len(fresh) <= config.more_than:
            continue
        for index, _surface, start, end, _numbers in fresh:
            covered[index].append((start, end))
        surfaces: dict[str, int] = defaultdict(int)
        for _index, surface, _start, _end, _numbers in fresh:
            surfaces[surface] += 1
        shown = max(surfaces, key=lambda item: (surfaces[item], -len(item)))
        numbers: set[int] = set()
        for _index, _surface, _start, _end, found_on in fresh:
            numbers.update(found_on)
        if any_line_suppressed(lines, numbers, rule_id="repeated-phrase", category="repetition"):
            continue
        first = min(fresh, key=lambda item: (min(item[4]), item[2]))
        sentence = sentences[first[0]]
        count = len(fresh)
        places = ", ".join(_place(item, sentences) for item in fresh[:8])
        extra = "" if len(fresh) <= 8 else f", and {len(fresh) - 8} more"
        suggestion = (
            f"Repeated {count} times ({places}{extra}). "
            "Cut the later copies, or say it a different way."
        )
        findings.append(finding_at(
            path, sentence.origins, first[2], first[3], sentence.line,
            severity=config.severity,
            category="repetition",
            rule_id="repeated-phrase",
            match=shown,
            suggestion=suggestion,
        ))
    return findings


def _place(hit: tuple, sentences: list[Sentence]) -> str:
    sentence = sentences[hit[0]]
    if sentence.origins:
        line, column = sentence.origins[min(hit[2], len(sentence.origins) - 1)]
        return f"line {line}:{column}"
    return f"line {sentence.line}"


def _ngrams(
    sentence: Sentence,
    min_n: int,
    max_n: int,
    *,
    max_gap: int = 3,
) -> list[tuple[tuple[str, ...], str, int, int, set[int]]]:
    """Content-word windows. `max_gap` is how many tokens may sit between content words."""
    masked = sentence.masked
    tokens: list[tuple[str, int, int, bool]] = []
    for match in TOKEN_RE.finditer(masked):
        word = match.group(0)
        tokens.append((word, match.start(), match.end(), is_content_word(word)))
    content_at = [index for index, token in enumerate(tokens) if token[3]]
    found: list[tuple[tuple[str, ...], str, int, int, set[int]]] = []
    if len(content_at) < min_n:
        return found
    for size in range(min_n, max_n + 1):
        if len(content_at) < size:
            break
        for offset in range(0, len(content_at) - size + 1):
            chosen = content_at[offset:offset + size]
            if any(chosen[pos + 1] - chosen[pos] - 1 > max_gap for pos in range(size - 1)):
                continue
            words = tuple(norm_token(tokens[index][0]) for index in chosen)
            start = tokens[chosen[0]][1]
            end = tokens[chosen[-1]][2]
            surface = _surface(masked[start:end])
            if not surface:
                continue
            numbers = _lines_for(sentence, start, end)
            found.append((words, surface, start, end, numbers))
    return found


def _lines_for(sentence: Sentence, start: int, end: int) -> set[int]:
    if not sentence.origins:
        return {sentence.line}
    last = min(max(end - 1, 0), len(sentence.origins) - 1)
    first = min(max(start, 0), len(sentence.origins) - 1)
    return {sentence.origins[first][0], sentence.origins[last][0]}


def _near_findings(
    sentences: list[Sentence],
    lines: list[LineInfo],
    path: str,
    config: RepetitionConfig,
) -> list[Finding]:
    prepared: list[tuple[Sentence, list[str]]] = []
    for sentence in sentences:
        tokens = _normalize(sentence.text)
        if len(tokens) >= config.near_min_words:
            prepared.append((sentence, tokens))
    if len(prepared) < 2:
        return _passage_findings(sentences, lines, path, config, set())
    parent = list(range(len(prepared)))
    pair_score: dict[tuple[int, int], float] = {}

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for left in range(len(prepared)):
        left_tokens = prepared[left][1]
        for right in range(left + 1, len(prepared)):
            right_tokens = prepared[right][1]
            ratio_len = len(left_tokens) / len(right_tokens)
            if ratio_len < 0.67 or ratio_len > 1.5:
                continue
            left_set = set(left_tokens)
            right_set = set(right_tokens)
            overlap = len(left_set & right_set) / len(left_set | right_set)
            if overlap < config.near_threshold - 0.2:
                continue
            score = SequenceMatcher(None, left_tokens, right_tokens).ratio()
            if score >= config.near_threshold:
                union(left, right)
                pair_score[(left, right)] = score
    clusters: dict[int, list[int]] = defaultdict(list)
    for index in range(len(prepared)):
        clusters[find(index)].append(index)
    findings: list[Finding] = []
    reported: set[int] = set()
    for members in clusters.values():
        if len(members) < 2:
            continue
        reported.update(id(prepared[index][0]) for index in members)
        anchor = members[0]
        others = members[1:]
        scores = []
        for other in others:
            key = (anchor, other) if anchor < other else (other, anchor)
            if key in pair_score:
                scores.append(pair_score[key])
        score = max(scores) if scores else config.near_threshold
        sentence = prepared[anchor][0]
        other_lines = ", ".join(str(prepared[index][0].line) for index in others)
        numbers = {prepared[index][0].line for index in members}
        if any_line_suppressed(lines, numbers, rule_id="near-duplicate", category="repetition"):
            continue
        snippet = _surface(sentence.text)
        if len(snippet) > 80:
            snippet = snippet[:77].rstrip() + "..."
        suggestion = (
            f"Near-duplicate of the sentence on line {other_lines} "
            f"(similarity {score:.2f}). A passage repeated with small changes."
        )
        findings.append(Finding(
            path=path,
            line=sentence.line,
            column=sentence.origins[0][1] if sentence.origins else 1,
            end_line=sentence.origins[-1][0] if sentence.origins else sentence.line,
            end_column=(sentence.origins[-1][1] + 1) if sentence.origins else 1 + len(snippet),
            severity=config.severity,
            category="repetition",
            rule_id="near-duplicate",
            match=snippet,
            suggestion=suggestion,
        ))
    findings.extend(_passage_findings(sentences, lines, path, config, reported))
    return findings


def _passage_findings(
    sentences: list[Sentence],
    lines: list[LineInfo],
    path: str,
    config: RepetitionConfig,
    already: set[int],
) -> list[Finding]:
    """Windows of consecutive sentences, when the sentences themselves did not match.

    `already` holds id() values of sentences reported by the sentence pass.
    """
    width = config.passage_sentences
    if width < 2 or len(sentences) < width * 2:
        return []
    windows: list[tuple[int, list[str], Sentence]] = []
    for start in range(0, len(sentences) - width + 1):
        chunk = sentences[start:start + width]
        tokens: list[str] = []
        for sentence in chunk:
            tokens.extend(_normalize(sentence.text))
        if len(tokens) >= config.passage_min_words:
            windows.append((start, tokens, chunk[0]))
    findings: list[Finding] = []
    used: set[int] = set()
    for left in range(len(windows)):
        if windows[left][0] in used:
            continue
        for right in range(left + 1, len(windows)):
            if windows[left][0] + width > windows[right][0]:
                continue
            # Skip when the sentence-level pass already paired these sentences.
            left_ids = range(windows[left][0], windows[left][0] + width)
            right_ids = range(windows[right][0], windows[right][0] + width)
            if any(id(sentences[index]) in already for index in left_ids):
                continue
            if any(id(sentences[index]) in already for index in right_ids):
                continue
            score = SequenceMatcher(None, windows[left][1], windows[right][1]).ratio()
            if score < config.passage_threshold:
                continue
            anchor = windows[left][2]
            other = windows[right][2]
            numbers = {anchor.line, other.line}
            if any_line_suppressed(lines, numbers, rule_id="near-duplicate", category="repetition"):
                continue
            snippet = _surface(anchor.text)
            if len(snippet) > 80:
                snippet = snippet[:77].rstrip() + "..."
            findings.append(Finding(
                path=path,
                line=anchor.line,
                column=anchor.origins[0][1] if anchor.origins else 1,
                end_line=anchor.line,
                end_column=(anchor.origins[0][1] + len(snippet)) if anchor.origins else 1 + len(snippet),
                severity=config.severity,
                category="repetition",
                rule_id="near-duplicate",
                match=snippet,
                suggestion=(
                    f"Near-duplicate passage, also around line {other.line} "
                    f"(similarity {score:.2f}). A passage repeated with small changes."
                ),
            ))
            used.add(windows[left][0])
            used.add(windows[right][0])
            break
    return findings
