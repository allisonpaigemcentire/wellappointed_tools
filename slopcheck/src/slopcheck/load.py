"""Load pattern files and the jargon dictionary, and merge a user overlay."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path

import yaml

BUCKETS = ("keep", "define", "replace", "cut")
SEVERITY_RANK = {"keep": 0, "define": 1, "replace": 2, "cut": 2}
JARGON_START = "<!-- jargon-data:start -->"
JARGON_END = "<!-- jargon-data:end -->"


class ConfigError(Exception):
    """A rules file or a jargon file is missing a field, or a regex is bad."""


@dataclass
class Pattern:
    id: str
    category: str
    severity: str
    pattern: str
    suggestion: str
    rx: re.Pattern


@dataclass
class EmDashRule:
    enabled: bool = True
    severity: str = "warning"
    max_per_window: int = 2
    window_words: int = 300
    suggestion: str = "Use a period or a comma."


@dataclass
class RuleSet:
    patterns: list[Pattern] = field(default_factory=list)
    em_dash: EmDashRule = field(default_factory=EmDashRule)


def packaged_text(name: str) -> str:
    return files("slopcheck").joinpath("data", name).read_text(encoding="utf-8")


def alias_regex(alias: str) -> str:
    """Literal alias: case-insensitive, hyphen or space, optional plural, word-bounded.

    The bounds use a lookaround on word characters so a hyphenated form still
    matches, and so the alias does not fire inside a longer word.
    """
    parts = [p for p in re.split(r"[\s-]+", alias.strip()) if p]
    body = r"[\s-]+".join(re.escape(p) for p in parts)
    tail = r"(?:s|es)?" if alias[-1:].isalpha() else ""
    return r"(?<![\w])" + body + tail + r"(?![\w])"


def compile_regex(pattern: str, *, where: str) -> re.Pattern:
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        raise ConfigError(f"{where}: bad regex {pattern!r}: {exc}") from exc


def _reject_em_dash(value: object, where: str) -> None:
    if isinstance(value, str):
        if "\u2014" in value:
            raise ConfigError(f"{where}: em dash in the entry. Rewrite it without one.")
    elif isinstance(value, dict):
        for item in value.values():
            _reject_em_dash(item, where)
    elif isinstance(value, list):
        for item in value:
            _reject_em_dash(item, where)


def _compile_entry(entry: dict, where: str) -> dict:
    if not isinstance(entry, dict) or not entry.get("term") or not entry.get("plain"):
        raise ConfigError(f"{where}: every entry needs term and plain")
    bucket = entry.get("bucket")
    if bucket not in BUCKETS:
        raise ConfigError(f"{where}: bucket must be one of {', '.join(BUCKETS)}")
    if not isinstance(entry.get("false_friend"), bool):
        raise ConfigError(f"{where}: false_friend must be true or false")
    if entry["false_friend"] and bucket == "keep":
        raise ConfigError(f"{where}: a false friend always gets a definition, so it can't be in keep")
    _reject_em_dash(entry, where)
    compiled: list[tuple[str, re.Pattern]] = []
    for alias in entry.get("aliases") or []:
        if not isinstance(alias, str) or not alias.strip():
            raise ConfigError(f"{where}: aliases must be strings")
        compiled.append((alias, compile_regex(alias_regex(alias), where=where)))
    for pattern in entry.get("regex") or []:
        if not isinstance(pattern, str):
            raise ConfigError(f"{where}: regex entries must be strings")
        compiled.append((pattern, compile_regex(pattern, where=where)))
    if not compiled:
        raise ConfigError(f"{where}: needs at least one alias or regex")
    stored = dict(entry)
    stored["rx"] = compiled
    return stored


def jargon_yaml_text(text: str, path: str) -> str:
    """Return YAML for a dictionary file.

    A Markdown file carries the entries in a fenced yaml block between
    jargon-data markers. A YAML file is the entries themselves.
    """
    if JARGON_START in text or JARGON_END in text:
        if JARGON_START not in text or JARGON_END not in text:
            raise ConfigError(f"{path}: no {JARGON_START} … {JARGON_END} block")
        inner = text.split(JARGON_START, 1)[1].split(JARGON_END, 1)[0]
        match = re.search(r"```ya?ml\s*\n(.*?)\n```", inner, re.S)
        if not match:
            raise ConfigError(f"{path}: the jargon-data block has no fenced yaml section")
        return match.group(1)
    return text


def parse_jargon(text: str, path: str = "jargon") -> list[dict]:
    raw = jargon_yaml_text(text, path)
    try:
        data = yaml.safe_load(raw) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: bad YAML: {exc}") from exc
    if isinstance(data, list):
        items = data
    else:
        items = data.get("entries") or []
    entries: list[dict] = []
    seen: set[str] = set()
    for index, entry in enumerate(items, 1):
        term = entry.get("term", "?") if isinstance(entry, dict) else "?"
        where = f"{path}: entry {index} ({term})"
        stored = _compile_entry(entry, where)
        key = stored["term"].lower()
        if key in seen:
            raise ConfigError(f"{where}: duplicate term")
        seen.add(key)
        entries.append(stored)
    if not entries:
        raise ConfigError(f"{path}: no entries")
    return entries


def load_jargon(path: Path | None = None) -> list[dict]:
    if path is None:
        return parse_jargon(packaged_text("jargon.yaml"), "jargon.yaml")
    file = Path(path)
    if not file.exists():
        raise ConfigError(f"jargon dictionary missing: {file}")
    return parse_jargon(file.read_text(encoding="utf-8"), str(file))


def _pattern_from(raw: dict, where: str) -> Pattern:
    if not isinstance(raw, dict) or not raw.get("id"):
        raise ConfigError(f"{where}: a pattern needs an id")
    for key in ("category", "severity", "pattern", "suggestion"):
        if not raw.get(key):
            raise ConfigError(f"{where}: pattern {raw.get('id')!r} needs {key}")
    if raw["severity"] not in ("error", "warning"):
        raise ConfigError(f"{where}: pattern {raw['id']!r} severity must be error or warning")
    return Pattern(
        id=str(raw["id"]),
        category=str(raw["category"]),
        severity=str(raw["severity"]),
        pattern=str(raw["pattern"]),
        suggestion=str(raw["suggestion"]),
        rx=compile_regex(str(raw["pattern"]), where=f"{where}: pattern {raw['id']}"),
    )


def _em_dash_from(raw: dict | None, base: EmDashRule | None = None) -> EmDashRule:
    current = base or EmDashRule()
    raw = raw or {}
    severity = raw.get("severity", current.severity)
    if severity not in ("error", "warning"):
        raise ConfigError("em_dash.severity must be error or warning")
    try:
        cap = int(raw.get("max_per_window", current.max_per_window))
        window = int(raw.get("window_words", current.window_words))
    except (TypeError, ValueError) as exc:
        raise ConfigError("em_dash max_per_window and window_words must be integers") from exc
    if window < 1:
        raise ConfigError("em_dash.window_words must be at least 1")
    enabled = raw.get("enabled", current.enabled)
    if not isinstance(enabled, bool):
        raise ConfigError("em_dash.enabled must be true or false")
    return EmDashRule(
        enabled=enabled,
        severity=severity,
        max_per_window=cap,
        window_words=window,
        suggestion=str(raw.get("suggestion", current.suggestion)),
    )


def parse_rules(text: str, path: str = "rules") -> tuple[list[dict], EmDashRule, bool, list[str]]:
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: bad YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: the rules file must be a mapping")
    patterns = data.get("patterns") or []
    if not isinstance(patterns, list):
        raise ConfigError(f"{path}: patterns must be a list")
    disable = data.get("disable") or []
    if not isinstance(disable, list):
        raise ConfigError(f"{path}: disable must be a list of pattern ids")
    return patterns, _em_dash_from(data.get("em_dash")), bool(data.get("replace")), [str(item) for item in disable]


def load_rules(path: Path | None = None) -> RuleSet:
    if path is None:
        patterns, em_dash, _replace, disable = parse_rules(packaged_text("rules.yaml"), "rules.yaml")
        if disable:
            raise ConfigError("rules.yaml: the shipped file should not disable its own patterns")
        return RuleSet(patterns=[_pattern_from(item, "rules.yaml") for item in patterns], em_dash=em_dash)
    file = Path(path)
    if not file.exists():
        raise ConfigError(f"rules file missing: {file}")
    return merge_rules(load_rules(None), file.read_text(encoding="utf-8"), str(file))


def merge_rules(base: RuleSet, text: str, path: str, extra_disable: list[str] | None = None) -> RuleSet:
    patterns, em_dash, replace, disable = parse_rules(text, path)
    # The user's em_dash block was parsed against defaults. Re-apply it on top of base.
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: bad YAML: {exc}") from exc
    em_dash = _em_dash_from(data.get("em_dash"), base.em_dash) if not replace else _em_dash_from(data.get("em_dash"), base.em_dash)
    by_id: dict[str, dict] = {}
    if not replace:
        for pattern in base.patterns:
            by_id[pattern.id] = {
                "id": pattern.id,
                "category": pattern.category,
                "severity": pattern.severity,
                "pattern": pattern.pattern,
                "suggestion": pattern.suggestion,
            }
    for item in disable + list(extra_disable or []):
        by_id.pop(str(item), None)
    for item in patterns:
        if not isinstance(item, dict) or not item.get("id"):
            raise ConfigError(f"{path}: a pattern needs an id")
        current = by_id.get(str(item["id"]), {})
        by_id[str(item["id"])] = {**current, **item}
    compiled = [_pattern_from(item, path) for item in by_id.values()]
    return RuleSet(patterns=compiled, em_dash=em_dash)


def merge_jargon(base: list[dict], text: str, path: str, extra_disable: list[str] | None = None) -> list[dict]:
    raw = jargon_yaml_text(text, path)
    try:
        data = yaml.safe_load(raw) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: bad YAML: {exc}") from exc
    if isinstance(data, list):
        payload = {"entries": data}
    else:
        payload = data
    replace = bool(payload.get("replace"))
    disable = [str(item).lower() for item in (payload.get("disable") or [])]
    disable += [str(item).lower() for item in (extra_disable or [])]
    by_term: dict[str, dict] = {}
    if not replace:
        for entry in base:
            stored = {key: value for key, value in entry.items() if key != "rx"}
            by_term[entry["term"].lower()] = stored
    for term in disable:
        by_term.pop(term, None)
    for item in payload.get("entries") or []:
        if not isinstance(item, dict) or not item.get("term"):
            raise ConfigError(f"{path}: an entry needs a term")
        key = str(item["term"]).lower()
        current = {} if replace else by_term.get(key, {})
        # A user list replaces that field. Omitted fields stay.
        by_term[key] = {**current, **item}
    entries = []
    for index, entry in enumerate(by_term.values(), 1):
        where = f"{path}: entry {index} ({entry.get('term', '?')})"
        entries.append(_compile_entry(entry, where))
    if not entries:
        raise ConfigError(f"{path}: no entries left after merge")
    return entries


def apply_em_dash_overrides(rules: RuleSet, overrides: dict | None) -> RuleSet:
    if not overrides:
        return rules
    rules.em_dash = _em_dash_from(overrides, rules.em_dash)
    return rules


def disable_patterns(rules: RuleSet, ids: list[str]) -> RuleSet:
    blocked = {item.lower() for item in ids}
    if not blocked:
        return rules
    rules.patterns = [pattern for pattern in rules.patterns if pattern.id.lower() not in blocked]
    return rules


def disable_terms(entries: list[dict], terms: list[str]) -> list[dict]:
    blocked = {item.lower() for item in terms}
    if not blocked:
        return entries
    kept = [entry for entry in entries if entry["term"].lower() not in blocked]
    if not kept:
        raise ConfigError("every jargon term was disabled")
    return kept
