"""Report scaffolding."""

from pathlib import Path

import pytest

from agentdebug.report import init_report, render_report, slugify, template_text

REQUIRED = [
    "## Bottom line",
    "## First upstream failure",
    "## Suspected causes",
    "## Findings, ranked",
    "## Transition matrix",
    "## Minimal repro",
    "## Proposed fix",
    "## Hand-off",
    "N-1 replay",
    "`path:line`",
]


def test_template_has_the_review_sections():
    text = template_text()
    for heading in REQUIRED:
        assert heading in text


def test_render_fills_title_and_date():
    body = render_report("Desk lamp checkout")
    assert "# Review: Desk lamp checkout" in body
    assert "{{name}}" not in body
    assert "Date: " in body
    assert "Date:\n" not in body


def test_init_writes_and_refuses_to_clobber(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    destination = init_report("Desk lamp checkout")
    assert destination == tmp_path / "Desk-lamp-checkout.md"
    assert destination.read_text(encoding="utf-8").startswith("# Review: Desk lamp checkout")
    with pytest.raises(FileExistsError):
        init_report("Desk lamp checkout")
    again = init_report("Desk lamp checkout", force=True)
    assert again == destination


def test_explicit_output_path(tmp_path: Path):
    target = tmp_path / "notes" / "review.md"
    written = init_report("Desk lamp", out=target)
    assert written == target
    assert target.is_file()


def test_path_like_names_stay_inside_one_segment():
    assert slugify("../etc/passwd") == "etc-passwd"
    assert "/" not in slugify("a/b")
    with pytest.raises(ValueError):
        slugify("..")
    with pytest.raises(ValueError):
        slugify("   ")
