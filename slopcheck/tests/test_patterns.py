"""Each slop category fires on the tell and stays quiet on ordinary prose."""

import pytest

from slopcheck.check import check_text
from slopcheck.load import load_jargon, load_rules

RULES = load_rules()
JARGON = load_jargon()


def hits(text, category=None):
    found = check_text(text, "t.md", RULES, JARGON)
    if category:
        return [item for item in found if item.category == category or item.label() == category]
    return found


@pytest.mark.parametrize("line", [
    "We should delve into the logs.",
    "The essay is a tapestry of ideas.",
    "Let's dive in.",
    "In today's rapidly evolving landscape, teams wait.",
    "This will unlock the potential of the cache.",
])
def test_ai_tell_flags(line):
    found = hits(line + "\n", "ai-tell")
    assert found, line
    assert found[0].severity == "error"
    assert found[0].column >= 1
    assert found[0].suggestion


def test_ai_tell_column():
    found = hits("Please delve now.\n", "ai-tell")
    assert found[0].line == 1
    assert found[0].column == 8
    assert found[0].match == "delve"


@pytest.mark.parametrize("line", [
    "We should look at the logs.",
    "Here is the file the team kept.",
])
def test_ai_tell_plain_lines(line):
    assert hits(line + "\n", "ai-tell") == []


@pytest.mark.parametrize("line", [
    "It isn't just automation, it's a choice.",
    "The workflows aren't just scripts, they're a paradigm shift.",
    "Not only the tests, but the docs were stale.",
    "It's not about speed, it's about the failing test.",
    "Not because the file was new, but because the tests failed.",
])
def test_contrast_frame_flags(line):
    assert hits(line + "\n", "contrast-frame"), line


def test_contrast_frame_plain():
    assert hits("The tests failed on the second run.\n", "contrast-frame") == []


@pytest.mark.parametrize("line", [
    "The result? Review time doubled.",
    "Here's the thing: the files were stale.",
    "Here’s the thing about context files.",
    "The answer? Fewer files.",
    "The catch? The cache was cold.",
])
def test_reveal_fragment_flags(line):
    found = hits(line + "\n", "reveal-fragment")
    assert found, line
    assert found[0].severity == "error"


@pytest.mark.parametrize("line", [
    "The result was a 4% drop in review time.",
    "Here is the file the team kept.",
    "The answer came from the second run.",
])
def test_reveal_fragment_plain(line):
    assert hits(line + "\n", "reveal-fragment") == []


@pytest.mark.parametrize("line", [
    "The bottom line is that review load grew.",
    "Ultimately, the team cut the file.",
    "In conclusion, the cache was cold.",
    "In summary, the tests failed.",
])
def test_summary_closer_flags(line):
    found = hits(line + "\n", "summary-closer")
    assert found, line


def test_summary_closer_plain():
    assert hits("The bottom of the log showed the error.\n", "summary-closer") == []


@pytest.mark.parametrize("line", [
    "It's important to note that the cache was cold.",
    "It is worth noting that the file was stale.",
    "When it comes to caching, the file was stale.",
    "The proxy plays a key role in the outage.",
    "At the end of the day, the tests failed.",
])
def test_filler_hedge_flags(line):
    found = hits(line + "\n", "filler-hedge")
    assert found, line
    assert found[0].severity == "error"


def test_filler_hedge_warning_does_not_look_like_an_error():
    found = hits("Use the tool in order to install packages.\n", "filler-hedge")
    assert found and found[0].severity == "warning"
    assert found[0].rule_id == "in-order-to"


def test_significance_tail_flags_the_comma_form():
    found = hits("The cache was cold, highlighting a missing warm-up.\n", "significance-tail")
    assert found
    assert found[0].severity == "warning"
    assert found[0].match.startswith(",")


def test_significance_tail_ignores_a_main_verb():
    assert hits("The report is highlighting the cold cache.\n", "significance-tail") == []


def test_one_em_dash_is_quiet():
    assert hits("The file was stale — nobody noticed.\n", "em-dash") == []


def test_em_dash_density_warns():
    found = hits("One — two — three — done.\n", "em-dash")
    assert len(found) == 1
    assert found[0].severity == "warning"
    assert found[0].match == "—"
    assert "limit is 2 per 300" in found[0].suggestion


def test_spaced_hyphen_counts_as_an_em_dash():
    text = "One -- two -- three -- done.\n"
    assert hits(text, "em-dash")


def test_quotes_and_code_are_not_scanned_for_patterns():
    assert hits('She said "let\'s dive in" and stopped.\n') == []
    assert hits("Use `delve` as the verb name in the example.\n") == []
    fenced = "```\ndelve into this\n```\nThe prose is clean.\n"
    assert hits(fenced, "ai-tell") == []


def test_line_opt_out_for_a_pattern_and_a_category():
    assert hits("Let's dive in. <!-- slopcheck-ok: lets-dive-in -->\n", "ai-tell") == []
    assert hits("Let's dive in. <!-- slop-ok: ai-tell -->\n", "ai-tell") == []


def test_builtin_categories_exist():
    categories = {pattern.category for pattern in RULES.patterns}
    assert categories >= {
        "ai-tell",
        "contrast-frame",
        "reveal-fragment",
        "summary-closer",
        "filler-hedge",
        "significance-tail",
    }
