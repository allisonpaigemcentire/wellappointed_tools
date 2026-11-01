"""Scaffold a review report from the shared template."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

_TEMPLATE = Path(__file__).with_name("templates") / "review_report.md"
_SLUG = re.compile(r"[^A-Za-z0-9._-]+")


def template_text() -> str:
    return _TEMPLATE.read_text(encoding="utf-8")


def slugify(name: str) -> str:
    """Turn a review title into a single path segment."""
    slug = _SLUG.sub("-", name.strip())
    slug = re.sub(r"-{2,}", "-", slug).strip(".-_")
    if not slug or slug in {".", ".."} or "/" in slug or "\\" in slug:
        raise ValueError(f"review name {name!r} is empty or not a single path segment")
    return slug


def render_report(name: str) -> str:
    title = name.strip()
    if not title:
        raise ValueError("review name is empty")
    body = template_text().replace("{{name}}", title)
    today = date.today().isoformat()
    return body.replace("Date:", f"Date: {today}", 1)


def init_report(name: str, out: Path | None = None, force: bool = False) -> Path:
    """Write a review markdown file. Refuses to overwrite unless force is set."""
    slug = slugify(name)
    destination = out if out is not None else Path.cwd() / f"{slug}.md"
    destination = destination.expanduser()
    if destination.exists() and not force:
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(render_report(name), encoding="utf-8")
    return destination
