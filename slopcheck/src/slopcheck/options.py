"""Thresholds for the prose checks. Missing keys keep the defaults."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from slopcheck.load import ConfigError
from slopcheck.names import load_known_names


def _bool(value: object, where: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigError(f"{where} must be true or false")
    return value


def _severity(value: object, where: str) -> str:
    if value not in ("error", "warning"):
        raise ConfigError(f"{where} must be error or warning")
    return str(value)


def _int(value: object, where: str, *, low: int, high: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{where} must be an integer")
    if value < low or (high is not None and value > high):
        limit = f"at least {low}" if high is None else f"from {low} to {high}"
        raise ConfigError(f"{where} must be {limit}")
    return value


def _unit(value: object, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{where} must be a number from 0 to 1")
    number = float(value)
    if not 0 <= number <= 1:
        raise ConfigError(f"{where} must be from 0 to 1")
    return number


def _block(config: dict, key: str) -> dict:
    raw = config.get(key)
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ConfigError(f"{key} must be a mapping")
    return raw


@dataclass
class RepetitionConfig:
    enabled: bool = True
    severity: str = "warning"
    min_ngram: int = 4
    max_ngram: int = 5
    more_than: int = 2
    near_duplicate: bool = True
    near_threshold: float = 0.86
    near_min_words: int = 8
    passage_sentences: int = 2
    passage_min_words: int = 18
    passage_threshold: float = 0.88


@dataclass
class RhythmConfig:
    enabled: bool = True
    severity: str = "warning"
    long_words: int = 25
    long_share: float = 0.70
    cv_below: float = 0.15
    min_sentences: int = 8
    run_length: int = 5
    run_span: int = 3
    run_min_words: int = 8
    flag_long: bool = True
    flag_flat: bool = True
    flag_run: bool = True


@dataclass
class DamageConfig:
    enabled: bool = True
    severity: str = "warning"
    lowercase_start: bool = True
    doubled_words: bool = True
    duplicated_span: bool = True
    dangling_punct: bool = True
    # Opt-in. The pattern is narrow, and it still misfires on odd but grammatical lines.
    missing_function_word: bool = False


@dataclass
class BriefConfig:
    enabled: bool = True
    severity: str = "warning"
    overlap: float = 0.72
    ngram: int = 5
    min_content_words: int = 6


@dataclass
class CheckOptions:
    repetition: RepetitionConfig = field(default_factory=RepetitionConfig)
    rhythm: RhythmConfig = field(default_factory=RhythmConfig)
    damage: DamageConfig = field(default_factory=DamageConfig)
    brief: BriefConfig = field(default_factory=BriefConfig)
    known_names: set[str] = field(default_factory=set)
    show_rhythm: bool = False


def default_options() -> CheckOptions:
    return CheckOptions(known_names=load_known_names())


def _apply_repetition(base: RepetitionConfig, raw: dict) -> RepetitionConfig:
    current = replace(base)
    if "enabled" in raw:
        current.enabled = _bool(raw["enabled"], "repetition.enabled")
    if "severity" in raw:
        current.severity = _severity(raw["severity"], "repetition.severity")
    if "min_ngram" in raw:
        current.min_ngram = _int(raw["min_ngram"], "repetition.min_ngram", low=2, high=12)
    if "max_ngram" in raw:
        current.max_ngram = _int(raw["max_ngram"], "repetition.max_ngram", low=2, high=12)
    if "more_than" in raw:
        current.more_than = _int(raw["more_than"], "repetition.more_than", low=1, high=50)
    if "near_duplicate" in raw:
        current.near_duplicate = _bool(raw["near_duplicate"], "repetition.near_duplicate")
    if "near_threshold" in raw:
        current.near_threshold = _unit(raw["near_threshold"], "repetition.near_threshold")
    if "near_min_words" in raw:
        current.near_min_words = _int(raw["near_min_words"], "repetition.near_min_words", low=4, high=80)
    if "passage_sentences" in raw:
        current.passage_sentences = _int(raw["passage_sentences"], "repetition.passage_sentences", low=2, high=4)
    if "passage_min_words" in raw:
        current.passage_min_words = _int(raw["passage_min_words"], "repetition.passage_min_words", low=8, high=200)
    if "passage_threshold" in raw:
        current.passage_threshold = _unit(raw["passage_threshold"], "repetition.passage_threshold")
    if current.min_ngram > current.max_ngram:
        raise ConfigError("repetition.min_ngram cannot be above repetition.max_ngram")
    return current


def _apply_rhythm(base: RhythmConfig, raw: dict) -> RhythmConfig:
    current = replace(base)
    if "enabled" in raw:
        current.enabled = _bool(raw["enabled"], "rhythm.enabled")
    if "severity" in raw:
        current.severity = _severity(raw["severity"], "rhythm.severity")
    if "long_words" in raw:
        current.long_words = _int(raw["long_words"], "rhythm.long_words", low=8, high=120)
    if "long_share" in raw:
        current.long_share = _unit(raw["long_share"], "rhythm.long_share")
    if "cv_below" in raw:
        current.cv_below = _unit(raw["cv_below"], "rhythm.cv_below")
    if "min_sentences" in raw:
        current.min_sentences = _int(raw["min_sentences"], "rhythm.min_sentences", low=2, high=500)
    if "run_length" in raw:
        current.run_length = _int(raw["run_length"], "rhythm.run_length", low=3, high=40)
    if "run_span" in raw:
        current.run_span = _int(raw["run_span"], "rhythm.run_span", low=0, high=30)
    if "run_min_words" in raw:
        current.run_min_words = _int(raw["run_min_words"], "rhythm.run_min_words", low=1, high=80)
    for key in ("flag_long", "flag_flat", "flag_run"):
        if key in raw:
            setattr(current, key, _bool(raw[key], f"rhythm.{key}"))
    return current


def _apply_damage(base: DamageConfig, raw: dict) -> DamageConfig:
    current = replace(base)
    if "enabled" in raw:
        current.enabled = _bool(raw["enabled"], "edit_damage.enabled")
    if "severity" in raw:
        current.severity = _severity(raw["severity"], "edit_damage.severity")
    for key in (
        "lowercase_start",
        "doubled_words",
        "duplicated_span",
        "dangling_punct",
        "missing_function_word",
    ):
        if key in raw:
            setattr(current, key, _bool(raw[key], f"edit_damage.{key}"))
    return current


def _apply_brief(base: BriefConfig, raw: dict) -> BriefConfig:
    current = replace(base)
    if "enabled" in raw:
        current.enabled = _bool(raw["enabled"], "brief_check.enabled")
    if "severity" in raw:
        current.severity = _severity(raw["severity"], "brief_check.severity")
    if "overlap" in raw:
        current.overlap = _unit(raw["overlap"], "brief_check.overlap")
    if "ngram" in raw:
        current.ngram = _int(raw["ngram"], "brief_check.ngram", low=3, high=12)
    if "min_content_words" in raw:
        current.min_content_words = _int(raw["min_content_words"], "brief_check.min_content_words", low=3, high=40)
    return current


def brief_paths_from(config: dict) -> list[str]:
    """Paths from `brief` or `briefs`. A string or a list both work."""
    paths: list[str] = []
    for key in ("brief", "briefs"):
        if key not in config:
            continue
        raw = config[key]
        if isinstance(raw, str) and raw.strip():
            paths.append(raw.strip())
        elif isinstance(raw, list):
            for index, item in enumerate(raw, 1):
                if not isinstance(item, str) or not item.strip():
                    raise ConfigError(f"{key}: item {index} must be a path")
                paths.append(item.strip())
        else:
            raise ConfigError(f"{key} must be a path or a list of paths")
    return paths


def options_from_config(config: dict | None, base: CheckOptions | None = None) -> CheckOptions:
    config = config or {}
    current = base or default_options()
    names = set(current.known_names)
    if "known_names" in config:
        raw = config["known_names"]
        if not isinstance(raw, list):
            raise ConfigError("known_names must be a list of names")
        for index, item in enumerate(raw, 1):
            if not isinstance(item, str) or not item.strip():
                raise ConfigError(f"known_names: item {index} must be a name")
            names.add(item.strip().casefold())
    return CheckOptions(
        repetition=_apply_repetition(current.repetition, _block(config, "repetition")),
        rhythm=_apply_rhythm(current.rhythm, _block(config, "rhythm")),
        damage=_apply_damage(current.damage, _block(config, "edit_damage")),
        brief=_apply_brief(current.brief, _block(config, "brief_check")),
        known_names=names,
        show_rhythm=current.show_rhythm,
    )
