"""Edit-damage checks: leftovers from a bad automated edit.

On by default, as warnings: a lowercase sentence start, a doubled function
word ("the the"), a clause or sentence copied twice in one paragraph, and
dangling punctuation such as a comma left in front of a closing quote.

Missing-function-word stays off unless the config or `--function-words` asks
for it. The pattern is narrow on purpose.
"""

from __future__ import annotations

import re

from slopcheck.model import Finding, finding_at
from slopcheck.options import DamageConfig
from slopcheck.text import ABBR, LineInfo, ScanConfig, _join, line_suppressed, mask_text, prose_paragraphs
from slopcheck.tokens import word_count

# A sentence end, then a lowercase word. Abbreviations are filtered afterwards.
_LOWER = re.compile(r"""([.!?])(["”’)\]*_]*)(\s+)([a-z])""")
_DOUBLED = re.compile(
    r"\b(the|a|an|and|or|of|to|in|on|for|with|from|by|at|as|if|but|nor)\s+\1\b"
    r"|\b(the|a|an)\s+(the|a|an)\b",
    re.IGNORECASE,
)
# Comma, space, then a closing quote. A straight quote only counts when it does
# not open the next word, so `"one", "two"` stays quiet.
_DANGLING_QUOTE = re.compile(r""",\s+”|,\s+"(?!\w)|,\s+’(?!\w)""")
# A curly closer with a space before it, which English does not do.
_SPACE_CLOSER = re.compile(r"\s+”")
_SPACE_BEFORE = re.compile(r"[A-Za-z] +[,;]")
_DOUBLE_COMMA = re.compile(r",,")
# No opening quote in the sentence, but a closer sits after a comma.
_BARE_CLOSER = re.compile(r"\w, ?”")
_MISSING = re.compile(
    r"\b(?:the|an?)\s+of\b"
    r"|\b(?:the|an?)\s+to\s+(?:the|an?|be|do|have|get|make)\b",
    re.IGNORECASE,
)
_ROUGH_SPLIT = re.compile(r"""(?<=[.!?])["”’)\]*_]*\s+""")
_CLAUSE_SPLIT = re.compile(r"\s*[;]\s*|\s*,\s*")
_LEADING = re.compile(r"^(?:and|but|or|then)\s+", re.IGNORECASE)

_LOWER_ABBR = ("e.g.", "i.e.", "vs.", "etc.", "cf.", "approx.", "al.")
# After a closing quote, these verbs continue the sentence: "it?" cried she.
_DIALOGUE_TAG = re.compile(
    r"^(?:said|says|cried|asked|replied|answered|whispered|muttered|shouted|"
    r"called|added|continued|returned|exclaimed|observed|remarked|inquired|"
    r"demanded|began|went)\b",
    re.IGNORECASE,
)
_TITLE_ABBR = ("Mr.", "Ms.", "Mrs.", "Dr.", "St.", "No.", "Jr.", "Sr.", "Inc.", "Ltd.", "U.S.", "U.K.")


def damage_findings(
    lines: list[LineInfo],
    path: str,
    config: DamageConfig,
    scan: ScanConfig | None = None,
) -> list[Finding]:
    if not config.enabled:
        return []
    findings: list[Finding] = []
    findings.extend(_line_findings(lines, path, config, scan))
    findings.extend(_paragraph_findings(lines, path, config, scan))
    return findings


def _skip(lines: list[LineInfo], number: int, rule_id: str) -> bool:
    return line_suppressed(lines, number, rule_id=rule_id, category="edit-damage")


def _is_real(raw: str, masked: str, start: int, end: int) -> bool:
    """False when the span was blanked as code, a comment, or an editor note."""
    return raw[start:end] == masked[start:end]


def _line_findings(
    lines: list[LineInfo],
    path: str,
    config: DamageConfig,
    scan: ScanConfig | None,
) -> list[Finding]:
    findings: list[Finding] = []
    for line in lines:
        if line.kind != "body":
            continue
        raw = line.text
        masked = mask_text(raw, scan, quotes=False)
        origins = [(line.number, offset + 1) for offset in range(len(raw))]
        if config.doubled_words:
            for match in _DOUBLED.finditer(raw):
                if not _is_real(raw, masked, match.start(), match.end()):
                    continue
                if _skip(lines, line.number, "doubled-word"):
                    continue
                shown = re.sub(r"\s+", " ", match.group(0)).strip()
                findings.append(finding_at(
                    path, origins, match.start(), match.end(), line.number,
                    severity=config.severity,
                    category="edit-damage",
                    rule_id="doubled-word",
                    match=shown,
                    suggestion='Doubled word. Delete one copy ("the the").',
                ))
        if config.dangling_punct:
            findings.extend(_dangling_on_line(raw, masked, origins, lines, path, line.number, config))
        if config.missing_function_word:
            for match in _MISSING.finditer(raw):
                if not _is_real(raw, masked, match.start(), match.end()):
                    continue
                if _skip(lines, line.number, "missing-function-word"):
                    continue
                shown = re.sub(r"\s+", " ", match.group(0)).strip()
                findings.append(finding_at(
                    path, origins, match.start(), match.end(), line.number,
                    severity=config.severity,
                    category="edit-damage",
                    rule_id="missing-function-word",
                    match=shown,
                    suggestion="A function word looks missing. Read the sentence aloud before keeping it.",
                ))
    return findings


def _dangling_on_line(
    raw: str,
    masked: str,
    origins: list[tuple[int, int]],
    lines: list[LineInfo],
    path: str,
    number: int,
    config: DamageConfig,
) -> list[Finding]:
    if _skip(lines, number, "dangling-punct"):
        return []
    spans: list[tuple[int, int, str, str]] = []

    def add(match: re.Match[str], shown: str, detail: str) -> None:
        if _is_real(raw, masked, match.start(), match.end()):
            spans.append((match.start(), match.end(), shown, detail))

    for match in _DANGLING_QUOTE.finditer(raw):
        add(match, _clean(match.group(0)), "A comma was left in front of a closing quote.")
    for match in _SPACE_CLOSER.finditer(raw):
        add(match, "”", "A space was left before a closing quote.")
    for match in _SPACE_BEFORE.finditer(raw):
        add(match, _clean(match.group(0)), "A space was left before the punctuation.")
    for match in _DOUBLE_COMMA.finditer(raw):
        add(match, ",,", "Doubled comma.")
    if "“" not in raw:
        for match in _BARE_CLOSER.finditer(raw):
            add(match, _clean(match.group(0)), "A closing quote was left behind.")
    # Drop a later hit that sits inside an earlier one.
    spans.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    kept: list[tuple[int, int, str, str]] = []
    for span in spans:
        if any(other[0] <= span[0] and span[1] <= other[1] for other in kept):
            continue
        kept.append(span)
    findings: list[Finding] = []
    for start, end, shown, detail in kept:
        findings.append(finding_at(
            path, origins, start, end, number,
            severity=config.severity,
            category="edit-damage",
            rule_id="dangling-punct",
            match=shown,
            suggestion=detail + ' For example, ", ”" or "simply, ”" after the quoted words were cut.',
        ))
    return findings


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _paragraph_findings(
    lines: list[LineInfo],
    path: str,
    config: DamageConfig,
    scan: ScanConfig | None,
) -> list[Finding]:
    findings: list[Finding] = []
    if not config.lowercase_start and not config.duplicated_span:
        return findings
    for group in prose_paragraphs(lines):
        raw_parts = [(line.number, line.text) for line in group]
        masked_parts = [(line.number, mask_text(line.text, scan, quotes=False)) for line in group]
        text, origins = _join(raw_parts)
        masked, _masked_origins = _join(masked_parts)
        if config.lowercase_start:
            findings.extend(_lowercase(text, masked, origins, lines, path, config))
        if config.duplicated_span:
            findings.extend(_duplicates(text, masked, origins, lines, path, config))
    return findings


def _is_abbreviation(text: str, punct_index: int) -> bool:
    if text[punct_index] != ".":
        return False
    prefix = text[:punct_index + 1]
    if re.search(r"\b[A-Z]\.$", prefix) or re.search(r"\b[A-Z]\.[A-Z]\.$", prefix):
        return True
    for abbr in _LOWER_ABBR:
        if prefix[-len(abbr):].lower() == abbr:
            return True
    for abbr in _TITLE_ABBR:
        if prefix.endswith(abbr):
            return True
    for abbr in ABBR:
        if prefix.endswith(abbr):
            return True
    return False


def _starts_abbreviation(text: str, letter_at: int) -> bool:
    rest = text[letter_at:]
    return any(rest.lower().startswith(abbr) for abbr in _LOWER_ABBR)


def _lowercase(
    text: str,
    masked: str,
    origins: list[tuple[int, int]],
    lines: list[LineInfo],
    path: str,
    config: DamageConfig,
) -> list[Finding]:
    findings: list[Finding] = []
    for match in _LOWER.finditer(text):
        if not _is_real(text, masked, match.start(), match.end()):
            continue
        punct_at = match.start(1)
        if _is_abbreviation(text, punct_at):
            continue
        # An ellipsis of spaced dots is not a second sentence start at every dot.
        if text[punct_at] == "." and punct_at >= 2 and text[punct_at - 2:punct_at] == ". ":
            continue
        letter_at = match.start(4)
        if letter_at >= len(origins) or _starts_abbreviation(text, letter_at):
            continue
        if match.group(2).strip() and _DIALOGUE_TAG.match(text[letter_at:]):
            continue
        # "pre-commit" and similar tool names stay lowercase on purpose.
        token = re.match(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)+", text[letter_at:])
        if token:
            continue
        line, column = origins[letter_at]
        if _skip(lines, line, "lowercase-start"):
            continue
        shown = text[letter_at]
        findings.append(Finding(
            path=path,
            line=line,
            column=column,
            end_line=line,
            end_column=column + 1,
            severity=config.severity,
            category="edit-damage",
            rule_id="lowercase-start",
            match=shown,
            suggestion="This sentence starts with a lowercase letter. Capitalise it, or join it to the sentence before.",
        ))
    return findings


def _key(text: str) -> str:
    flat = text.casefold().replace("’", "'")
    flat = re.sub(r"[^a-z0-9'\s]", " ", flat)
    flat = _LEADING.sub("", flat.strip())
    return re.sub(r"\s+", " ", flat).strip()


def _protect(text: str) -> str:
    protected = text
    for abbr in ABBR:
        protected = protected.replace(abbr, abbr.replace(".", "\0"))
    return protected


def _duplicates(
    text: str,
    masked: str,
    origins: list[tuple[int, int]],
    lines: list[LineInfo],
    path: str,
    config: DamageConfig,
) -> list[Finding]:
    findings: list[Finding] = []
    protected = _protect(text)
    parts = _ROUGH_SPLIT.split(protected)
    seen: dict[str, int] = {}
    cursor = 0
    for part in parts:
        restored = part.replace("\0", ".")
        start = protected.find(part, cursor)
        if start < 0:
            start = cursor
        cursor = start + len(part)
        core = restored.strip()
        if not core:
            continue
        lead = restored.find(core)
        origin_at = start + max(lead, 0)
        key = _key(core)
        if word_count(core) >= 4 and key in seen:
            if origin_at < len(origins) and _is_real(text, masked, origin_at, min(len(text), origin_at + len(core))):
                line = origins[origin_at][0]
                if not _skip(lines, line, "duplicated-sentence"):
                    snippet = _clean(core)
                    if len(snippet) > 80:
                        snippet = snippet[:77].rstrip() + "..."
                    findings.append(finding_at(
                        path, origins, origin_at, origin_at + len(core), line,
                        severity=config.severity,
                        category="edit-damage",
                        rule_id="duplicated-sentence",
                        match=snippet,
                        suggestion="This sentence is repeated in the same paragraph. Delete one copy.",
                    ))
        elif word_count(core) >= 4:
            seen[key] = origin_at
        findings.extend(_clauses(core, origin_at, origins, lines, path, config))
    return findings


def _clauses(
    sentence: str,
    origin_at: int,
    origins: list[tuple[int, int]],
    lines: list[LineInfo],
    path: str,
    config: DamageConfig,
) -> list[Finding]:
    pieces = _CLAUSE_SPLIT.split(sentence)
    if len(pieces) < 2:
        return []
    seen: dict[str, str] = {}
    findings: list[Finding] = []
    search_from = 0
    for piece in pieces:
        core = piece.strip()
        if not core:
            continue
        at = sentence.find(core, search_from)
        if at < 0:
            at = search_from
        search_from = at + len(core)
        key = _key(core)
        if word_count(core) < 4 or not key:
            continue
        if key in seen:
            abs_at = origin_at + at
            if abs_at >= len(origins):
                continue
            line = origins[abs_at][0]
            if _skip(lines, line, "duplicated-clause"):
                continue
            snippet = _clean(core)
            if len(snippet) > 80:
                snippet = snippet[:77].rstrip() + "..."
            findings.append(finding_at(
                path, origins, abs_at, abs_at + len(core), line,
                severity=config.severity,
                category="edit-damage",
                rule_id="duplicated-clause",
                match=snippet,
                suggestion="This clause is repeated in the same sentence. Delete one copy.",
            ))
        else:
            seen[key] = core
    return findings
