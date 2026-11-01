"""Jargon buckets, aliases, and the first-use definition check."""

import pytest

from slopcheck.check import check_text
from slopcheck.load import ConfigError, load_jargon, load_rules, parse_jargon

RULES = load_rules()
JARGON = load_jargon()

MINI = """
entries:
- {term: widget, bucket: define, plain: a small part, false_friend: false, aliases: [widget]}
- {term: gizmo, bucket: define, plain: a tool that counts, false_friend: true, aliases: [gizmo]}
- {term: doohickey, bucket: replace, plain: say what it does, false_friend: false, aliases: [doohickey, "doo hickey"], regex: ['(?-i:\\bDHK\\b)']}
- {term: thingamajig-native, bucket: cut, plain: delete it, false_friend: false, aliases: [thingamajig-native]}
- {term: plainword, bucket: keep, plain: known to all, false_friend: false, aliases: [plainword]}
"""


@pytest.fixture
def mini():
    return parse_jargon(MINI, "mini.yaml")


def jargon_hits(text, entries=JARGON):
    return [item for item in check_text(text, "t.md", RULES, entries) if item.category == "jargon"]


@pytest.mark.parametrize("line,term", [
    ("Our agentic tools ran overnight.", "agentic"),
    ("The inference bill doubled.", "inference"),
    ("We tried few-shot prompting first.", "few-shot / in-context learning"),
    ("Every team is AI-native now.", "AI-native / AI-first"),
    ("An AI-first company ships faster.", "AI-native / AI-first"),
    ("The latest frontier models are better.", "frontier model"),
    ("This is a game-changer for reviews.", "10x / game-changer / supercharge"),
    ("Some vendors promise AGI next year.", "AGI"),
    ("The AI-enabled team shipped.", "AI-enabled"),
])
def test_replace_and_cut_block(line, term):
    found = jargon_hits(line + "\n")
    assert found, line
    assert found[0].severity == "error"
    assert found[0].rule_id == term
    assert found[0].bucket in ("replace", "cut")
    assert found[0].suggestion


def test_cut_suggestion_is_the_plain_translation():
    found = jargon_hits("The AI-enabled team shipped.\n")
    assert "delete it" in found[0].suggestion.lower()


def test_quotes_and_opt_out_are_exempt():
    text = (
        'The report title says "agentic AI" in it.\n\n'
        "The vendor calls it agentic. <!-- slop-ok: jargon -->\n"
    )
    assert jargon_hits(text) == []


def test_slopcheck_ok_spelling_also_works():
    text = "The vendor calls it agentic. <!-- slopcheck-ok: jargon -->\n"
    assert jargon_hits(text) == []


def test_front_matter_title_is_checked_and_slug_is_not():
    text = '---\ntitle: "Agentic tools, explained"\nslug: agentic-tools\n---\nPlain body.\n'
    found = jargon_hits(text)
    assert len(found) == 1
    assert found[0].line == 2
    assert found[0].column == 9
    assert found[0].match == "Agentic"


def test_keep_terms_never_flag():
    assert jargon_hits("Write a better prompt. Prompting takes an hour.\n") == []
    assert jargon_hits("GitHub Copilot reviews the diff.\n") == []


def test_generic_copilot_is_replace_and_the_product_name_is_not():
    found = jargon_hits("Use a copilot for the draft.\n")
    assert found and found[0].bucket == "replace"
    assert jargon_hits("Microsoft Copilot reviewed the diff.\n") == []


def test_lowercase_rag_is_not_the_acronym():
    assert jargon_hits("The rag was on the floor.\n") == []
    found = jargon_hits("The RAG pipeline ran.\n")
    assert found and found[0].severity == "warning"
    assert found[0].rule_id == "RAG"


def test_narrow_regexes_skip_ordinary_senses():
    assert jargon_hits("This is causal inference, not a lab result.\n") == []
    assert jargon_hits("This is statistical inference from the survey.\n") == []
    assert jargon_hits("Autonomous teams shipped the change.\n") == []
    assert jargon_hits("The autonomous loop ran for an hour.\n")
    assert jargon_hits("Institutional memory carried the practice.\n") == []
    assert jargon_hits("The agent memory file was stale.\n")
    assert jargon_hits("Add a hook to the story.\n") == []
    assert jargon_hits("A pre-tool hook blocked the push.\n")


def test_longer_match_wins_unless_the_shorter_one_is_stricter():
    defined = jargon_hits("Multi-agent, meaning several model runs that split a task, helped.\n")
    assert defined == []
    blocked = jargon_hits("The agentic workflow ran.\n")
    assert blocked and blocked[0].rule_id == "agentic"


def test_false_friend_warns_and_a_real_gloss_clears_it():
    bare = jargon_hits("Set the temperature low for repeatable output.\n")
    assert bare and bare[0].false_friend and bare[0].severity == "warning"
    assert "randomness" in bare[0].suggestion
    defined = jargon_hits("Temperature is a setting for how much randomness the model uses.\n")
    assert defined == []


@pytest.mark.parametrize("text", [
    "A widget, meaning a small part, holds the door.",
    "A widget (a small part) holds the door.",
    "A widget is a small part that holds the door.",
    "Widgets are the small parts that hold the door.",
    "Widget: a small part. It holds the door.",
    "It is what we call a widget in the shop.",
    "The team added a widget, which holds the door shut.",
    "The team added a widget, a small part, to the door.",
    "The team added a widget. That is, a small part that holds the door.",
    "The team added a widget to the door. A widget is a small part.",
    "The small part that holds the door (widget) broke.",
    "We added a widget,\nmeaning a small part, on Tuesday.",
])
def test_define_term_with_a_nearby_gloss_passes(mini, text):
    assert jargon_hits(text + "\n", mini) == []


def test_define_term_without_a_gloss_warns_once(mini):
    found = jargon_hits("The widget broke on Tuesday.\n\nWe replaced it on Friday.\n", mini)
    assert len(found) == 1
    assert found[0].severity == "warning"
    assert found[0].line == 1
    assert found[0].column == 5
    assert found[0].suggestion.startswith("Define it on first use:")
    assert "a small part" in found[0].suggestion.lower()


def test_only_the_first_use_counts(mini):
    assert jargon_hits("A widget is a small part.\n\nLater the widget broke again.\n", mini) == []
    late = jargon_hits("The widget broke.\n\nWe moved on.\n\nMuch later: a widget is a small part.\n", mini)
    assert late and late[0].line == 1


def test_a_gloss_two_sentences_later_is_too_late(mini):
    found = jargon_hits("The widget broke. We waited. A widget is a small part.\n", mini)
    assert found and found[0].line == 1


def test_a_quoted_first_use_is_skipped(mini):
    text = 'She said "the widget broke" loudly.\n\nA widget is a small part.\n'
    assert jargon_hits(text, mini) == []


def test_false_friend_label_on_a_mini_term(mini):
    found = jargon_hits("The gizmo broke.\n", mini)
    assert found and found[0].false_friend
    assert "a tool that counts" in found[0].suggestion.lower()


def test_aliases_plural_hyphen_and_case(mini):
    for line in ("The doohickey broke.", "Two doohickeys broke.", "The doo-hickey broke.", "The Doo Hickey broke.", "The DHK broke."):
        found = jargon_hits(line + "\n", mini)
        assert found and found[0].bucket == "replace", line
    assert jargon_hits("The dhk word and doohickeyish and xdoohickey are not hits.\n", mini) == []


def test_keep_mini_term_and_cut_mini_term(mini):
    assert jargon_hits("The plainword stays. Another plainword.\n", mini) == []
    found = jargon_hits("Be thingamajig-native.\n", mini)
    assert found and found[0].bucket == "cut" and found[0].severity == "error"


def test_replace_still_flags_when_a_gloss_is_present(mini):
    found = jargon_hits("A doohickey, meaning a gadget, broke.\n", mini)
    assert found and found[0].bucket == "replace"


def test_false_friend_cannot_be_keep():
    text = MINI.replace(
        "{term: plainword, bucket: keep, plain: known to all, false_friend: false",
        "{term: plainword, bucket: keep, plain: known to all, false_friend: true",
    )
    with pytest.raises(ConfigError, match="can't be in keep"):
        parse_jargon(text, "bad.yaml")


def test_bad_bucket_is_rejected():
    with pytest.raises(ConfigError, match="bucket must be one of"):
        parse_jargon(MINI.replace("bucket: cut", "bucket: avoid"), "bad.yaml")


def test_markdown_jargon_block_loads():
    wrapped = "intro\n<!-- jargon-data:start -->\n```yaml\n" + MINI + "```\n<!-- jargon-data:end -->\n"
    entries = parse_jargon(wrapped, "dict.md")
    assert {entry["term"] for entry in entries} == {
        "widget", "gizmo", "doohickey", "thingamajig-native", "plainword",
    }
