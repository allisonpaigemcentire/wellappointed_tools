"""List uncommon words that are not already in the jargon dictionary.

This needs the optional wordfreq package. A Zipf score under 3 is rare in
ordinary English, so the word is a candidate for the dictionary, not a failure.
"""

from __future__ import annotations

import re

from slopcheck.model import Suggestion
from slopcheck.text import ScanConfig, classify_lines, mask_text

TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9'+]*(?:-[A-Za-z0-9'+]+)*")
MIN_LENGTH = 4


class SuggestError(Exception):
    """wordfreq is not installed, or the suggester was asked to stop."""


def known_terms(entries: list[dict]) -> set[str]:
    known: set[str] = set()
    for entry in entries:
        known.add(entry["term"].lower())
        for part in re.split(r"[/,]", entry["term"]):
            token = part.strip().lower()
            if token:
                known.add(token)
        for alias in entry.get("aliases") or []:
            known.add(str(alias).lower())
        for pattern in entry.get("regex") or []:
            for word in re.findall(r"[A-Za-z][A-Za-z0-9'+-]{2,}", str(pattern)):
                known.add(word.lower())
    return known


def zipf_frequency(word: str) -> float:
    try:
        from wordfreq import zipf_frequency as freq
    except ImportError as exc:
        raise SuggestError(
            'The term suggester needs wordfreq. Install it with: pip install "slopcheck[suggest]"'
        ) from exc
    return float(freq(word, "en"))


def suggest_terms(
    text: str,
    entries: list[dict],
    *,
    zipf_below: float = 3.0,
    limit: int = 40,
    frequency=None,
    scan: ScanConfig | None = None,
) -> list[Suggestion]:
    """Return rare words not already in the dictionary, rarest first."""
    freq = frequency or zipf_frequency
    known = known_terms(entries)
    counts: dict[str, int] = {}
    first_line: dict[str, int] = {}
    for line in classify_lines(text, scan):
        if line.kind in {"code", "skip"}:
            continue
        source = line.title_value if line.kind == "title" and line.title_value is not None else line.text
        if line.kind == "front" and line.text.strip() in {"", "---"}:
            continue
        masked = mask_text(source, scan)
        for match in TOKEN_RE.finditer(masked):
            token = match.group(0)
            if len(token) < MIN_LENGTH:
                continue
            key = token.lower()
            if key in known or any(char.isdigit() for char in key):
                continue
            counts[key] = counts.get(key, 0) + 1
            first_line.setdefault(key, line.number)
    scored: list[Suggestion] = []
    for token, count in counts.items():
        score = freq(token)
        if score < zipf_below:
            scored.append(Suggestion(term=token, zipf=score, line=first_line[token], count=count))
    scored.sort(key=lambda item: (item.zipf, item.term))
    return scored[:limit]
