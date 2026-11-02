"""Opt-out notes, link glosses, editor notes, and unpublished sections."""

import json
from pathlib import Path

from slopcheck.check import check_text
from slopcheck.cli import main
from slopcheck.load import load_jargon, load_rules
from slopcheck.text import ScanConfig, compile_editor_notes, compile_skip_headings

RULES = load_rules()
JARGON = load_jargon()
FIXTURE = Path(__file__).parent / "fixtures" / "draft-notes.md"


def hits(text: str, scan: ScanConfig | None = None):
    return check_text(text if text.endswith("\n") else text + "\n", "t.md", RULES, JARGON, scan=scan)


def jargon(text: str, scan: ScanConfig | None = None):
    return [item for item in hits(text, scan) if item.category == "jargon"]


def test_opt_out_note_in_parentheses_is_not_part_of_the_id():
    text = (
        "The vendor calls it agentic. "
        "<!-- slop-ok: jargon (approved wording, Jordan Hale 2026-01-15) -->"
    )
    assert jargon(text) == []


def test_opt_out_note_after_a_dash_and_slopcheck_ok():
    assert hits("Let's dive in. <!-- slopcheck-ok: lets-dive-in - kept on purpose -->") == []
    found = hits("We should delve into the logs. <!-- slop-ok: ai-tell — section opener we want -->")
    assert all(item.category != "ai-tell" for item in found)
    assert jargon("The vendor calls it agentic. <!-- slopcheck-ok: jargon – approved wording -->") == []


def test_a_note_does_not_silence_a_different_rule():
    found = hits("We should delve into agentic tools. <!-- slop-ok: jargon (approved) -->")
    assert any(item.rule_id == "delve" for item in found)
    assert all(item.rule_id != "agentic" for item in found)


def test_markdown_link_is_not_a_gloss_and_the_url_is_not_checked():
    found = jargon("See [AI champions](https://example.com/champions) for the rollout.")
    assert len(found) == 1
    assert found[0].rule_id == "AI champions"
    assert found[0].severity == "warning"
    assert found[0].match.lower() == "ai champions"

    image = jargon("![frontier model](https://example.com/pic.png)")
    assert any(item.rule_id == "frontier model" and item.severity == "error" for item in image)

    relative = jargon("See [AI champions](champions.md) today.")
    assert any(item.rule_id == "AI champions" for item in relative)

    assert jargon(
        "AI champions (engineers given time to help their teams adopt AI tools) lead it."
    ) == []
    assert jargon(
        "See [AI champions](https://example.com) (engineers given time to help their teams adopt AI tools)."
    ) == []
    assert all(item.category != "ai-tell" for item in hits("Read the [docs](https://example.com/delve-into-this)."))
    assert any(item.rule_id == "lets-dive-in" for item in hits("Read [let's dive in](https://example.com/start) later."))


def test_editor_notes_and_html_comments_are_not_checked():
    assert jargon("The public line stays. [EDITOR: agentic is approved in this note]") == []
    assert jargon("<!-- agentic belongs in this comment -->") == []
    found = hits("We should delve here. [EDITOR: and also delve in the note]")
    assert [item.rule_id for item in found if item.rule_id == "delve"] == ["delve"]
    assert any(item.rule_id == "agentic" for item in jargon("[editor: agentic is not a capitalised note]"))
    quiet = hits("[EDITOR: one — two — three — done and it is a game-changer]")
    assert quiet == []


def test_unpublished_headings_skip_until_the_same_or_higher_level():
    text = """
## Claim trace

This agentic setup is a game-changer.

### Nested trace

Ultimately the trace stays internal.

## Published again

We should delve into the logs.

## Editor notes

In today's rapidly evolving landscape, teams wait.

## Not for publication

Let's dive in.

## Sources (not for publication)

It's important to note that the cache was cold.

## Claim-trace

The bottom line is the trace.

# After the notes

The tests passed on Tuesday.
"""
    found = hits(text)
    assert [(item.line, item.rule_id) for item in found] == [(12, "delve")]


def test_slopcheck_off_and_on_markers():
    text = """
<!-- slopcheck-off -->

The inference bill doubled.

<!-- slopcheck-on -->

We should delve into the logs.
"""
    found = hits(text)
    assert [item.rule_id for item in found] == ["delve"]
    assert hits("<!-- slopcheck-off -->\nWe should delve into the logs.\n") == []


def test_markers_inside_a_fence_do_not_toggle():
    text = "```\n<!-- slopcheck-off -->\n```\nWe should delve into the logs.\n"
    assert any(item.rule_id == "delve" for item in hits(text))


def test_config_replaces_skip_lists(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".slopcheck.yaml").write_text(
        "skip_headings: []\neditor_notes: []\n",
        encoding="utf-8",
    )
    path = tmp_path / "note.md"
    path.write_text(
        "## Claim trace\n\nThis agentic setup stays.\n\n[EDITOR: agentic too]\n",
        encoding="utf-8",
    )
    assert main(["--json", "--fail-on", "none", str(path)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert sum(1 for item in payload["findings"] if item["rule_id"] == "agentic") == 2

    (tmp_path / ".slopcheck.yaml").write_text(
        "skip_headings:\n  - Scratch\n",
        encoding="utf-8",
    )
    path.write_text("## Scratch\n\nWe should delve into the logs.\n\n## Next\n\nLet's dive in.\n", encoding="utf-8")
    assert main(["--json", "--fail-on", "none", str(path)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert [item["rule_id"] for item in payload["findings"]] == ["lets-dive-in"]


def test_bad_editor_note_pattern_exits_2(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".slopcheck.yaml").write_text("editor_notes:\n  - '['\n", encoding="utf-8")
    path = tmp_path / "note.md"
    path.write_text("Hello.\n", encoding="utf-8")
    assert main([str(path)]) == 2
    assert "editor_notes" in capsys.readouterr().err


def test_compile_helpers_reject_bad_lists():
    import pytest
    from slopcheck.load import ConfigError
    with pytest.raises(ConfigError):
        compile_editor_notes("nope")
    with pytest.raises(ConfigError):
        compile_skip_headings(["", "ok"])


def test_fixture_before_was_12_and_now_keeps_two_published_hits():
    """The same file produced 12 findings before these skips.

    Eleven were errors and one was a warning. The champions link was not
    among them, because the URL's parenthesis looked like a gloss. After the
    fix that link is flagged, and the opt-out, the editor note, the comment,
    the off/on stretch, and the unpublished headings are not.
    """
    text = FIXTURE.read_text(encoding="utf-8")
    found = check_text(text, "draft-notes.md", RULES, JARGON)
    assert len(found) == 2
    assert {(item.line, item.rule_id) for item in found} == {(5, "AI champions"), (21, "delve")}


def test_front_matter_is_checked_through_title_fields_only():
    text = (
        "---\n"
        "title: A plain title\n"
        "slug: delve-into-the-game-changer\n"
        "tags: [tapestry, paradigm-shift]\n"
        "---\n"
        "The tests passed.\n"
    )
    assert hits(text) == []
    flagged = hits("---\ntitle: Let us delve into it\n---\nThe tests passed.\n")
    assert [item.rule_id for item in flagged] == ["delve"]
    assert flagged[0].line == 2


def test_multi_line_html_comments_are_not_checked():
    text = (
        "<!-- Notes for the editor:\n"
        "     delve into the tapestry, it's a game-changer\n"
        "     and agentic too -->\n"
        "The tests passed.\n"
    )
    assert hits(text) == []
    assert jargon(text) == []


def test_text_after_a_multi_line_comment_closes_is_checked():
    text = "<!-- a note\nstill the note --> We should delve here.\n"
    found = [item for item in hits(text) if item.rule_id == "delve"]
    assert len(found) == 1
    assert (found[0].line, found[0].column) == (2, 30)


def test_text_before_an_open_comment_is_checked():
    text = "We should delve here. <!-- delve\ninto this tapestry -->\n"
    found = [item.rule_id for item in hits(text)]
    assert found.count("delve") == 1
    assert "tapestry" not in found


def test_a_comment_opener_in_inline_code_does_not_hide_the_page():
    text = "Write `<!--` to open a comment.\nWe should delve here.\n"
    assert [item.rule_id for item in hits(text) if item.rule_id == "delve"] == ["delve"]


def test_a_comment_opener_inside_a_fence_does_not_hide_the_page():
    text = "```html\n<!--\n```\nWe should delve here.\n"
    assert [item.rule_id for item in hits(text) if item.rule_id == "delve"] == ["delve"]


def test_rule_ids_in_disable_are_matched_without_case():
    from slopcheck.load import merge_rules

    merged = merge_rules(load_rules(), "disable: [Delve]\n", "rules.yaml")
    assert "delve" not in {pattern.id for pattern in merged.patterns}


def test_a_stray_comment_opener_in_prose_does_not_hide_the_page():
    for text in (
        'Type "<!--" to start a comment.\n\nWe should delve here.\n',
        "The arrow <!-- starts one.\n\nWe should delve here.\n",
        "The arrow <!-- starts one.\nWe should delve here.\n",
    ):
        assert [item.rule_id for item in hits(text) if item.rule_id == "delve"] == ["delve"], text


def test_a_comment_block_at_the_start_of_a_line_runs_to_the_end_when_unclosed():
    assert hits("<!--\nWe should delve\n\nStill delve\n") == []


def test_a_comment_inside_a_fence_does_not_open_and_text_after_is_checked():
    text = "~~~\n<!-- open\n~~~\nWe should delve.\n-->\n"
    assert [item.line for item in hits(text) if item.rule_id == "delve"] == [4]


def test_multi_line_comment_with_crlf_line_endings():
    text = "<!--\r\nWe should delve\r\n-->\r\nWe delve here.\r\n"
    assert [item.line for item in hits(text) if item.rule_id == "delve"] == [4]


def test_empty_and_blank_files_have_no_findings():
    assert hits("") == []
    assert hits("\n\n") == []
    assert hits("---\n") == []


def test_front_matter_after_a_byte_order_mark_is_still_front_matter():
    text = "\ufeff---\nslug: delve\ntitle: Let us delve\n---\nBody is fine.\n"
    assert [(item.line, item.rule_id) for item in hits(text)] == [(3, "delve")]


def test_front_matter_must_be_at_the_top():
    text = "Intro line.\n\n---\nslug: delve\n---\n"
    assert [item.line for item in hits(text) if item.rule_id == "delve"] == [4]


def test_a_page_that_opens_with_a_thematic_break_is_still_checked():
    text = "---\n\nWe should delve into this.\n\n---\n\nMore text.\n"
    assert [item.line for item in hits(text) if item.rule_id == "delve"] == [3]


# Regression cases from the 2026-11-02 Debugging Bot review.


def test_a_closer_inside_a_code_fence_does_not_close_a_mid_line_opener():
    text = "Type <!-- to open a comment.\n```\n-->\n```\nWe should delve here.\n"
    assert [item.rule_id for item in hits(text) if item.rule_id == "delve"] == ["delve"]


def test_front_matter_key_may_start_with_a_non_ascii_letter():
    text = "---\nñame: Notes\nslug: delve-into-the-tapestry\n---\nThe tests passed.\n"
    assert hits(text) == []
