"""Repeated phrases, briefs, rhythm, edit damage, and baseline diffs."""

from dataclasses import replace

from slopcheck.check import check_text
from slopcheck.cli import main
from slopcheck.load import load_jargon, load_rules
from slopcheck.options import default_options

RULES = load_rules()
JARGON = load_jargon()


def hits(text, category=None, **kwargs):
    found = check_text(text if text.endswith("\n") else text + "\n", "t.md", RULES, JARGON, **kwargs)
    if category:
        return [item for item in found if item.category == category]
    return found


def test_repeated_content_phrase_reports_count_and_location():
    text = """
During the storm the small brass lantern swung above the table while cold rain pressed the glass.

After the argument the small brass lantern swung above the table, though Mara had already left.

By breakfast the small brass lantern swung above the table and the bread was gone.
"""
    found = hits(text, "repetition")
    phrases = [item for item in found if item.rule_id == "repeated-phrase"]
    assert phrases, found
    assert "3 times" in phrases[0].suggestion or "Repeated 3" in phrases[0].suggestion
    assert "small brass lantern" in phrases[0].match
    assert phrases[0].line == 2
    assert phrases[0].severity == "warning"


def test_function_word_runs_do_not_count_as_a_repeated_phrase():
    text = "\n".join(["The of the of the of the end."] * 6)
    assert [item for item in hits(text, "repetition") if item.rule_id == "repeated-phrase"] == []


def test_quoted_phrase_and_headings_are_not_repeated_phrase_hits():
    text = """
# The small brass lantern swung above the table

She said "the small brass lantern swung above the table" once.

She said "the small brass lantern swung above the table" again.

She said "the small brass lantern swung above the table" a third time.
"""
    assert [item for item in hits(text, "repetition") if item.rule_id == "repeated-phrase"] == []


def test_near_duplicate_speech():
    text = """
"We leave at dawn," Mara told the crew, "and nobody boards the boat without a lamp or a coat."

Jonah repeated the order so the new hands would hear it. "We leave at dawn," Mara told the crew, "and nobody boards the ship without a lamp or a coat."
"""
    found = [item for item in hits(text, "repetition") if item.rule_id == "near-duplicate"]
    assert found, hits(text)
    assert "similarity" in found[0].suggestion
    assert found[0].line == 2


def test_brief_leak_flags_a_close_copy_and_skips_an_intended_quote():
    brief = """
The harbor closes at dusk because the old lighthouse lamp has failed and the channel is unmarked.

<!-- slopcheck-quotes -->
The east pier stays open for fishing boats until the lamp is repaired.
<!-- /slopcheck-quotes -->
"""
    text = """
The harbor closes at dusk because the old lighthouse lamp has failed and the channel is unmarked.

The east pier stays open for fishing boats until the lamp is repaired.

Bring a coat if you walk the west beach after dark and tell the harbormaster which boat you took.
"""
    found = hits(text, "brief-leak", briefs=[brief])
    assert len(found) == 1
    assert found[0].line == 2
    assert found[0].rule_id == "brief-leak"
    assert "brief" in found[0].suggestion.lower()


def test_brief_inline_marker_is_an_allowlist():
    brief = "The tide book is on the nail by the south door. <!-- slopcheck-quote -->\n"
    text = "The tide book is on the nail by the south door.\n"
    assert hits(text, "brief-leak", briefs=[brief]) == []


def test_no_brief_means_no_leak_findings():
    text = "The harbor closes at dusk because the old lighthouse lamp has failed and the channel is unmarked.\n"
    assert hits(text, "brief-leak") == []


def test_rhythm_flags_a_flat_run_and_reports_the_numbers():
    sentences = [
        "Mara counted twelve wooden crates beside the south wall.",
        "Jonah mended one torn sail during the long lunch hour.",
        "The cook boiled white beans with salt and dried pepper.",
        "A gull watched the empty pier from the tall stone post.",
        "Children raced three dogs along the wet gray sand.",
        "The clerk locked both doors after the last bell rang.",
        "Fishers stacked clean nets under the low tin roof.",
        "Lamps burned in six windows across the little bay.",
    ]
    found = hits("\n".join(sentences), "rhythm")
    ids = {item.rule_id for item in found}
    assert "rhythm-flat" in ids
    assert "rhythm-run" in ids
    flat = next(item for item in found if item.rule_id == "rhythm-flat")
    assert "Mean" in flat.suggestion
    assert "coefficient of variation" in flat.suggestion
    assert "25+" in flat.suggestion or "25+ words" in flat.suggestion


def test_rhythm_stays_quiet_on_a_short_varied_note():
    text = "The tests passed on Tuesday. One file was new. The other file was not, and the log explained why in a much longer sentence than the first two.\n"
    assert hits(text, "rhythm") == []


def test_dialogue_share_is_mentioned_when_speech_is_present():
    # Eight sentences, four of them mostly quoted, lengths deliberately uneven so
    # the flat-rhythm warning stays off and only the long-sentence share can fire.
    text = """
"Go now and take the lamp with you before the tide turns back," Mara said.
Jonah nodded.
"The east stair is slick and the rail is loose, so use the other stair," she said.
He went.
"Tell the harbormaster we need the spare coil and the dry matches," Mara said.
The door shut.
"Do not wait on the pier if the wind rises above the roof of the shed," she called.
He waved.
"""
    # Varied lengths should not be flat. Force the long threshold down so a warning
    # carries the dialogue number, by using the default only if a warning exists.
    options = default_options()
    options.rhythm = replace(options.rhythm, long_share=0.0, flag_flat=False, flag_run=False, min_sentences=4)
    found = hits(text, "rhythm", options=options)
    assert found
    assert "Dialogue share" in found[0].suggestion


def test_edit_damage_flags_the_common_leftovers():
    text = """
The lamp fell. the glass cracked on the stone floor.

The the door stuck in the frame.

The lamp was lit before dawn, the lamp was lit before dawn.

She said the line was simple and then stopped, ”

The crew waited quietly. The crew waited quietly.
"""
    found = hits(text, "edit-damage")
    ids = {item.rule_id for item in found}
    assert "lowercase-start" in ids
    assert "doubled-word" in ids
    assert "duplicated-clause" in ids
    assert "dangling-punct" in ids
    assert "duplicated-sentence" in ids
    lower = next(item for item in found if item.rule_id == "lowercase-start")
    assert lower.match == "t"
    doubled = next(item for item in found if item.rule_id == "doubled-word")
    assert doubled.match.lower() == "the the"


def test_abbreviations_and_that_that_are_not_edit_damage():
    text = (
        "Mr. Bennet replied that he had not. Dr. Hale said that that was the point. "
        "e.g. the sample stays. U.S. ships left at noon. "
        "Install the hook. pre-commit loads it from this directory. "
        "“Do you want to know?” cried his wife, impatiently.\n"
    )
    ids = {item.rule_id for item in hits(text, "edit-damage")}
    assert "lowercase-start" not in ids
    assert "doubled-word" not in ids


def test_missing_function_word_is_off_until_asked():
    text = "The crew sailed the of the channel before dusk.\n"
    assert [item for item in hits(text, "edit-damage") if item.rule_id == "missing-function-word"] == []
    options = default_options()
    options.damage = replace(options.damage, missing_function_word=True)
    found = hits(text, "edit-damage", options=options)
    assert any(item.rule_id == "missing-function-word" for item in found)


def test_opt_out_silences_a_new_check():
    text = 'The the door stuck. <!-- slopcheck-ok: doubled-word -->\n'
    assert [item for item in hits(text, "edit-damage") if item.rule_id == "doubled-word"] == []


def test_baseline_cli_reports_new_and_fixed(tmp_path, capsys):
    old = tmp_path / "old.md"
    new = tmp_path / "new.md"
    old.write_text("Please delve now.\n", encoding="utf-8")
    new.write_text("Please look now. The the lamp fell.\n", encoding="utf-8")
    code = main(["--baseline", str(old), "--json", str(new)])
    import json
    payload = json.loads(capsys.readouterr().out)
    rules = {item["rule_id"] for item in payload["findings"]}
    fixed = {item["rule_id"] for item in payload["fixed"]}
    assert "doubled-word" in rules
    assert "delve" in fixed
    assert "delve" not in rules
    assert payload["summary"]["fixed"] == 1
    # A warning does not fail the default run. The old error was fixed.
    assert code == 0
    assert payload["ok"] is True


def test_diff_command_matches_baseline(tmp_path, capsys):
    old = tmp_path / "old.md"
    new = tmp_path / "new.md"
    old.write_text("Please delve now.\n", encoding="utf-8")
    new.write_text("The tests passed on Tuesday.\n", encoding="utf-8")
    assert main(["diff", str(old), str(new)]) == 0
    out = capsys.readouterr().out
    assert "No new findings" in out
    assert "fixed:" in out
    assert "delve" in out


def test_exclude_category_still_drops_a_new_check():
    text = "The the door stuck in the frame.\n"
    assert hits(text, "edit-damage", exclude={"edit-damage"}) == []


def test_em_dash_window_count_matches_on_a_long_document():
    from slopcheck.check import check_text
    from slopcheck.load import load_rules

    rules = load_rules()
    filler = "word " * 400
    text = filler + "one — two — three — four — five.\n"
    found = [item for item in check_text(text, "t.md", rules, None) if item.rule_id == "em-dash"]
    assert len(found) == 1
    assert found[0].suggestion.startswith(f"4 em dashes in {rules.em_dash.window_words} words")
