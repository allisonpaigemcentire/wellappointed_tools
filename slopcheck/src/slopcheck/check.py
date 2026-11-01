"""Run pattern, em-dash, and jargon checks."""

from __future__ import annotations

import re
from pathlib import Path

from slopcheck.load import SEVERITY_RANK, RuleSet
from slopcheck.model import Finding
from slopcheck.text import (
    ScanConfig,
    Sentence,
    body_sentences,
    classify_lines,
    front_sentences,
    mask_text,
    normalize,
    suppressed,
)

WORD = re.compile(r"[A-Za-z0-9]+(?:['’.-][A-Za-z0-9]+)*")
EMDASH = re.compile(r"—| -- ")

# A definition sits in the same sentence or the next one. The markers are a
# heuristic: "the agent is a mess" looks defined, and a human still reads the gloss.
JARGON_AFTER = re.compile(
    r"""^["”’'*_`)\]]*\s*(?:"""
    r""",\s*(?:meaning|which|or|an?|that is|i\.e\.|short for|also called)\b"""
    r"""|\s*\(|\s*:\s|\s+[–-]\s"""
    r"""|\s+(?:is|are)\s+(?:a|an|the|what|when|where|how|any|just|simply|shorthand|short for)\b"""
    r"""|\s+(?:means|mean|refers? to|stands? for)\b)""",
    re.I,
)
JARGON_BEFORE = re.compile(
    r"""(?:what\s+(?:we|people|vendors|you|they|the industry|researchers|engineers)\s+calls?|called|known as|dubbed|so-called)"""
    r"""\s*["“‘'*_`]*\s*(?:(?:a|an|the)\s+)?$|\(\s*$""",
    re.I,
)
JARGON_NEXT_OPENER = re.compile(
    r"""^["“*_`(]*(?:that is|in other words|put simply|meaning|this means|that means|by that|"""
    r"""(?:it|this|that|they|these|those)\s+(?:is|are|means|refers)\b|it's\s+an?\b)""",
    re.I,
)

PROSE_SUFFIXES = {".md", ".markdown", ".txt", ".rst", ".adoc"}
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".eggs"}


def _clean_match(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _finding_at(
    path: str,
    origins: list[tuple[int, int]] | None,
    start: int,
    end: int,
    fallback_line: int,
    *,
    severity: str,
    category: str,
    rule_id: str,
    match: str,
    suggestion: str,
    bucket: str | None = None,
    false_friend: bool = False,
) -> Finding:
    if origins:
        start = min(max(start, 0), len(origins) - 1)
        last = min(max(end - 1, 0), len(origins) - 1)
        line, column = origins[start]
        end_line, end_column = origins[last]
        end_column += 1
    else:
        line = column = end_line = fallback_line
        end_column = column + len(match)
    return Finding(
        path=path,
        line=line,
        column=column,
        end_line=end_line,
        end_column=end_column,
        severity=severity,
        category=category,
        rule_id=rule_id,
        match=match,
        suggestion=suggestion,
        bucket=bucket,
        false_friend=false_friend,
    )


def pattern_findings(
    lines: list,
    path: str,
    rules: RuleSet,
    exclude: set[str],
    scan: ScanConfig | None = None,
) -> list[Finding]:
    findings: list[Finding] = []
    for line in lines:
        if line.kind == "code" or line.kind == "skip":
            continue
        if line.kind == "title" and line.title_value is not None and line.title_column is not None:
            masked = mask_text(line.title_value, scan)
            origins = [(line.number, line.title_column + offset) for offset in range(len(masked))]
            searchable = masked
        elif line.kind in ("body", "front") and line.text.strip() not in {"", "---"}:
            masked = mask_text(line.text, scan)
            origins = [(line.number, offset + 1) for offset in range(len(masked))]
            searchable = masked
        else:
            continue
        for pattern in rules.patterns:
            if pattern.category in exclude or pattern.id in exclude:
                continue
            for match in pattern.rx.finditer(searchable):
                shown = _clean_match(match.group(0))
                if not shown:
                    continue
                if suppressed(line.keys, rule_id=pattern.id, category=pattern.category, bucket=None):
                    continue
                findings.append(_finding_at(
                    path, origins, match.start(), match.end(), line.number,
                    severity=pattern.severity,
                    category=pattern.category,
                    rule_id=pattern.id,
                    match=shown,
                    suggestion=pattern.suggestion,
                ))
    return findings


def emdash_findings(
    lines: list,
    path: str,
    rules: RuleSet,
    scan: ScanConfig | None = None,
) -> list[Finding]:
    rule = rules.em_dash
    if not rule.enabled:
        return []
    stream: list[tuple] = []
    for line in lines:
        if line.kind != "body":
            continue
        # Keep dashes inside quotes. Drop code, comments, link URLs, and editor notes.
        visible = mask_text(line.text, scan, quotes=False)
        events: list[tuple[int, str, re.Match[str]]] = []
        for match in WORD.finditer(visible):
            events.append((match.start(), "w", match))
        for match in EMDASH.finditer(visible):
            events.append((match.start(), "d", match))
        for _pos, kind, match in sorted(events, key=lambda item: item[0]):
            if kind == "w":
                stream.append(("w", line.number, match.start() + 1, ""))
            else:
                raw = match.group(0)
                dash_at = match.start() + (1 if raw.startswith(" ") else 0)
                shown = "—" if "—" in raw else "--"
                stream.append(("d", line.number, dash_at + 1, shown))
    words = [index for index, item in enumerate(stream) if item[0] == "w"]
    dashes = [(index, item) for index, item in enumerate(stream) if item[0] == "d"]
    if not dashes:
        return []
    cap = rule.max_per_window
    window = rule.window_words
    breaches: list[tuple[int, int, int, int]] = []
    if len(words) <= window:
        if len(dashes) > cap:
            breaches.append((0, len(dashes), 0, max(len(stream) - 1, 0)))
    else:
        for start in range(0, len(words) - window + 1):
            lo = words[start]
            hi = words[start + window - 1]
            count = sum(1 for index, _item in dashes if lo <= index <= hi)
            if count > cap:
                breaches.append((start, count, lo, hi))
    if not breaches:
        return []
    clusters: list[list[tuple[int, int, int, int]]] = []
    for breach in breaches:
        if not clusters or breach[0] > clusters[-1][-1][0] + 1:
            clusters.append([breach])
        else:
            clusters[-1].append(breach)
    findings: list[Finding] = []
    for cluster in clusters:
        worst = max(cluster, key=lambda item: item[1])
        _start, count, lo, hi = worst
        inside = [item for index, item in dashes if lo <= index <= hi]
        if not inside:
            continue
        # Point at the dash that crossed the limit.
        picked = inside[min(cap, len(inside) - 1)]
        span = len(words) if len(words) <= window else window
        suggestion = (
            f"{count} em dashes in {span} words (limit is {cap} per {window}). {rule.suggestion}"
        )
        findings.append(Finding(
            path=path,
            line=picked[1],
            column=picked[2],
            end_line=picked[1],
            end_column=picked[2] + len(picked[3]),
            severity=rule.severity,
            category="em-dash",
            rule_id="em-dash",
            match=picked[3],
            suggestion=suggestion,
        ))
    return findings


def jargon_matches(text: str, entries: list[dict]) -> list[tuple[int, int, dict, str]]:
    """Non-overlapping matches. A longer match wins unless the shorter one is stricter."""
    candidates: list[tuple[int, int, dict, str]] = []
    for entry in entries:
        for _source, pattern in entry["rx"]:
            candidates.extend(
                (match.start(), match.end(), entry, match.group(0))
                for match in pattern.finditer(text)
            )
    kept: list[tuple[int, int, dict, str]] = []
    for candidate in candidates:
        beaten = any(
            other[2] is not candidate[2]
            and other[0] <= candidate[0]
            and candidate[1] <= other[1]
            and (other[1] - other[0]) > (candidate[1] - candidate[0])
            and SEVERITY_RANK[other[2]["bucket"]] >= SEVERITY_RANK[candidate[2]["bucket"]]
            for other in candidates
        )
        if not beaten:
            kept.append(candidate)
    kept.sort(key=lambda item: (item[0], -item[1]))
    unique: list[tuple[int, int, dict, str]] = []
    seen: set[tuple[int, int]] = set()
    for candidate in kept:
        key = (id(candidate[2]), candidate[0])
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def defined_near(sentence: str, nxt: str | None, start: int, end: int, entry: dict) -> bool:
    """True when a gloss sits in this sentence or the next one."""
    if JARGON_AFTER.match(sentence[end:]) or JARGON_BEFORE.search(sentence[:start]):
        return True
    if not nxt:
        return False
    if JARGON_NEXT_OPENER.match(nxt.strip()):
        return True
    for _source, pattern in entry["rx"]:
        for match in pattern.finditer(nxt):
            if JARGON_AFTER.match(nxt[match.end():]) or JARGON_BEFORE.search(nxt[:match.start()]):
                return True
    return False


def _lead(text: str) -> str:
    text = text.strip()
    if text and text[0].isalpha() and text[0].islower():
        return text[0].upper() + text[1:]
    return text


def _jargon_suggestion(entry: dict) -> str:
    plain = _lead(str(entry["plain"]))
    if entry["bucket"] in ("replace", "cut"):
        return plain
    return f"Define it on first use: {plain}"


def _line_keys(lines, number: int) -> set[str]:
    for line in lines:
        if line.number == number:
            return line.keys
    return set()


def jargon_findings(
    lines: list,
    path: str,
    entries: list[dict],
    exclude: set[str],
    scan: ScanConfig | None = None,
) -> list[Finding]:
    front = front_sentences(lines, scan)

    def skips_jargon(sentence: Sentence) -> bool:
        keys = _line_keys(lines, sentence.line)
        return bool(keys & {"*", "all", "jargon"})

    # A line opted out of jargon is not a first use, and it is not the "next sentence".
    body = [sentence for sentence in body_sentences(lines, scan) if not skips_jargon(sentence)]
    findings: list[Finding] = []
    seen_first: set[int] = set()

    def consider(sentence: Sentence, nxt: str | None, *, allow_define: bool) -> None:
        keys = _line_keys(lines, sentence.line)
        for start, end, entry, matched in jargon_matches(sentence.masked, entries):
            bucket = entry["bucket"]
            if bucket == "keep":
                continue
            if bucket in exclude or "jargon" in exclude or entry["term"].lower() in exclude:
                continue
            if suppressed(keys, rule_id=entry["term"], category="jargon", bucket=bucket):
                continue
            shown = _clean_match(matched)
            if not shown:
                continue
            if bucket in ("replace", "cut"):
                findings.append(_finding_at(
                    path, sentence.origins, start, end, sentence.line,
                    severity="error",
                    category="jargon",
                    rule_id=entry["term"],
                    match=shown,
                    suggestion=_jargon_suggestion(entry),
                    bucket=bucket,
                    false_friend=bool(entry["false_friend"]),
                ))
            elif allow_define and (bucket == "define" or entry["false_friend"]) and id(entry) not in seen_first:
                seen_first.add(id(entry))
                if not defined_near(sentence.masked, nxt, start, end, entry):
                    findings.append(_finding_at(
                        path, sentence.origins, start, end, sentence.line,
                        severity="warning",
                        category="jargon",
                        rule_id=entry["term"],
                        match=shown,
                        suggestion=_jargon_suggestion(entry),
                        bucket=bucket,
                        false_friend=bool(entry["false_friend"]),
                    ))

    for sentence in front:
        consider(sentence, None, allow_define=False)
    for index, sentence in enumerate(body):
        nxt = body[index + 1].masked if index + 1 < len(body) else None
        consider(sentence, nxt, allow_define=True)
    return findings


def check_text(
    text: str,
    path: str = "<stdin>",
    rules: RuleSet | None = None,
    jargon: list[dict] | None = None,
    exclude: set[str] | None = None,
    scan: ScanConfig | None = None,
) -> list[Finding]:
    """Check one document. `jargon` None skips the dictionary."""
    if rules is None:
        from slopcheck.load import load_rules
        rules = load_rules()
    blocked = {item.lower() for item in (exclude or set())}
    lines = classify_lines(normalize(text), scan)
    findings = pattern_findings(lines, path, rules, blocked, scan)
    findings.extend(emdash_findings(lines, path, rules, scan))
    if jargon is not None:
        findings.extend(jargon_findings(lines, path, jargon, blocked, scan))
    findings = [item for item in findings if item.category not in blocked and item.rule_id.lower() not in blocked]
    findings.sort(key=lambda item: (item.line, item.column, item.rule_id))
    return findings


def iter_prose_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    found: list[Path] = []
    for file in path.rglob("*"):
        if not file.is_file():
            continue
        if any(part in SKIP_DIRS for part in file.parts):
            continue
        if file.suffix.lower() in PROSE_SUFFIXES:
            found.append(file)
    return sorted(found)


def read_document(path: Path) -> str | None:
    """Return text, or None when the file looks binary."""
    raw = path.read_bytes()
    if b"\0" in raw[:8192]:
        return None
    return raw.decode("utf-8", errors="replace")


def check_paths(
    paths: list[Path],
    rules: RuleSet,
    jargon: list[dict] | None,
    exclude: set[str] | None = None,
    scan: ScanConfig | None = None,
) -> tuple[list[Finding], int, list[str]]:
    """Check files. Returns findings, file count, and notes about skipped files."""
    findings: list[Finding] = []
    notes: list[str] = []
    count = 0
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(str(path))
        files = iter_prose_files(path)
        if path.is_dir() and not files:
            notes.append(f"no markdown or text files under {path}")
            continue
        for file in files:
            text = read_document(file)
            if text is None:
                notes.append(f"skipped binary file {file}")
                continue
            count += 1
            findings.extend(check_text(text, str(file), rules, jargon, exclude, scan))
    findings.sort(key=lambda item: (item.path, item.line, item.column, item.rule_id))
    return findings, count, notes
