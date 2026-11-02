"""Compare findings in an edited file with findings in the original.

A finding is new when the edited text has a hit the original did not. A
finding is fixed when the original had a hit the edit removed. Line numbers
are not part of the comparison, so a paragraph that moved does not look new.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import replace

from slopcheck.model import Finding

# Rhythm hits are one per document. The numbers in the match change when the
# prose changes, so the rule id is the whole identity.
_DOCUMENT_RULES = {"rhythm-flat", "rhythm-long", "rhythm-run"}


def fingerprint(finding: Finding) -> tuple[str, str, str]:
    if finding.rule_id in _DOCUMENT_RULES or finding.category == "rhythm":
        return (finding.category, finding.rule_id, "")
    match = re.sub(r"\s+", " ", finding.match).strip().casefold()
    return (finding.category, finding.rule_id, match)


def compare_findings(
    baseline: list[Finding],
    edited: list[Finding],
) -> tuple[list[Finding], list[Finding]]:
    """Return `(introduced, fixed)`.

    `fixed` findings keep the baseline location and use severity `fixed`, so
    they do not fail the run.
    """
    baseline_counts = Counter(fingerprint(item) for item in baseline)
    introduced: list[Finding] = []
    for item in edited:
        key = fingerprint(item)
        if baseline_counts[key] > 0:
            baseline_counts[key] -= 1
        else:
            introduced.append(item)
    edited_counts = Counter(fingerprint(item) for item in edited)
    seen: Counter[tuple[str, str, str]] = Counter()
    fixed: list[Finding] = []
    for item in baseline:
        key = fingerprint(item)
        seen[key] += 1
        if seen[key] > edited_counts[key]:
            fixed.append(replace(item, severity="fixed"))
    return introduced, fixed
