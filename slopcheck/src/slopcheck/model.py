"""Shared types for a slopcheck run."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Finding:
    path: str
    line: int
    column: int
    end_line: int
    end_column: int
    severity: str
    category: str
    rule_id: str
    match: str
    suggestion: str
    bucket: str | None = None
    false_friend: bool = False

    def label(self) -> str:
        if self.bucket:
            return f"jargon/{self.bucket}"
        return self.category

    def to_dict(self) -> dict:
        data = asdict(self)
        data["match"] = self.match
        return data


@dataclass
class Summary:
    files: int = 0
    errors: int = 0
    warnings: int = 0

    @property
    def findings(self) -> int:
        return self.errors + self.warnings

    def add(self, items: list[Finding]) -> None:
        for item in items:
            if item.severity == "error":
                self.errors += 1
            elif item.severity == "warning":
                self.warnings += 1

    def to_dict(self) -> dict:
        return {
            "files": self.files,
            "errors": self.errors,
            "warnings": self.warnings,
            "findings": self.findings,
        }


def over_threshold(summary: Summary, max_errors: int, max_warnings: int) -> bool:
    """True when errors or warnings pass their limits.

    A limit below 0 means that severity does not fail the run.
    """
    if max_errors >= 0 and summary.errors > max_errors:
        return True
    if max_warnings >= 0 and summary.warnings > max_warnings:
        return True
    return False


@dataclass
class Suggestion:
    term: str
    zipf: float
    line: int
    count: int = 1

    def to_dict(self) -> dict:
        return {"term": self.term, "zipf": round(self.zipf, 2), "line": self.line, "count": self.count}


@dataclass
class RunResult:
    findings: list[Finding] = field(default_factory=list)
    summary: Summary = field(default_factory=Summary)
    suggestions: list[Suggestion] | None = None
