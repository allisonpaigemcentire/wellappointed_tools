"""Sentence-initial capitals are not names unless the document shows they are."""

from slopcheck.check import check_text
from slopcheck.load import load_jargon, load_rules
from slopcheck.options import default_options
from slopcheck.suggest import suggest_terms

RULES = load_rules()
JARGON = load_jargon()


def hits(text, **kwargs):
    return check_text(text if text.endswith("\n") else text + "\n", "t.md", RULES, JARGON, **kwargs)


def test_sentence_initial_foster_is_still_the_verb():
    found = [item for item in hits("Foster the habit in the new team.") if item.rule_id == "foster"]
    assert found


def test_lowercase_foster_is_still_the_verb():
    found = [item for item in hits("The plan will foster growth.") if item.rule_id == "foster"]
    assert found


def test_a_mid_sentence_capital_confirms_the_name():
    text = "Ada met Foster at the dock. Foster signed the form."
    assert [item for item in hits(text) if item.rule_id == "foster"] == []


def test_a_known_name_counts_at_sentence_start():
    options = default_options()
    options.known_names.add("foster")
    found = [item for item in hits("Foster signed the form.", options=options) if item.rule_id == "foster"]
    assert found == []


def test_wrapped_line_is_not_a_rhetorical_opener():
    wrapped = "She wanted to know if he would\nHave you ever opened the log.\n"
    assert [item for item in hits(wrapped) if item.rule_id == "rhetorical-opener"] == []
    real = "The file was stale.\nHave you ever opened the log.\n"
    assert any(item.rule_id == "rhetorical-opener" for item in hits(real))
    mid = "Fine. Have you ever opened the log.\n"
    assert any(item.rule_id == "rhetorical-opener" for item in hits(mid))


def test_in_todays_does_not_match_inside_another_word():
    assert [item for item in hits("We will spin today's world into a tale.") if item.rule_id == "in-todays-world"] == []
    assert any(item.rule_id == "in-todays-world" for item in hits("In today's world, the team waited."))


def test_sentence_initial_copilot_is_not_assumed_to_be_the_product():
    found = [item for item in hits("Copilot reviewed the diff.") if item.category == "jargon"]
    assert found
    assert found[0].bucket == "replace"
    assert "copilot" in found[0].rule_id


def test_mid_sentence_copilot_is_the_product_name():
    assert [item for item in hits("GitHub Copilot reviews the diff.") if item.category == "jargon"] == []


def test_a_later_mid_sentence_copilot_confirms_the_sentence_start():
    text = "Copilot reviewed the diff.\n\nWe kept GitHub Copilot on.\n"
    assert [item for item in hits(text) if item.category == "jargon"] == []


def test_sentence_initial_pip_is_not_the_package_tool():
    assert [item for item in hits("Pip walked into the room.") if item.rule_id == "uv / pip"] == []


def test_suggest_skips_a_confirmed_name_and_keeps_a_sentence_start_capital(tmp_path=None):
    def freq(word: str) -> float:
        return 1.0 if word == "xyzzyplugh" else 5.0

    only_start = "Xyzzyplugh opened the door.\n"
    suggested = [item.term for item in suggest_terms(only_start, JARGON, frequency=freq)]
    assert "xyzzyplugh" in suggested

    confirmed = "Mara met Xyzzyplugh at the door. Xyzzyplugh waved.\n"
    suggested = [item.term for item in suggest_terms(confirmed, JARGON, frequency=freq)]
    assert "xyzzyplugh" not in suggested

    known = suggest_terms("Xyzzyplugh opened the door.\n", JARGON, frequency=freq, known_names={"xyzzyplugh"})
    assert [item.term for item in known] == []
