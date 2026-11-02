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


@pytest.mark.parametrize("line", [
    "It's not just about speed — it's about the failing test.",
    "It's not just about speed, it's about the failing test.",
    "It is not about speed; it is about the failing test.",
    "The release isn't merely a patch; it's a new model.",
    "The workflows aren't just scripts — they're a paradigm shift.",
    "The migration wasn't simply a rename -- it's a rewrite.",
    "We don't just ship code. We ship outcomes.",
    "They don't merely test the agent — they audit it.",
])
def test_contrast_frame_flags_other_separators(line):
    assert hits(line + "\n", "contrast-frame"), line


@pytest.mark.parametrize("line", [
    "It isn't fast; the cache is cold.",
    "We don't just guess.",
    "The release isn't ready. The tests are red.",
    "It's not about the money.",
])
def test_contrast_frame_other_separators_plain(line):
    assert hits(line + "\n", "contrast-frame") == [], line


@pytest.mark.parametrize("line, rule", [
    ("This will unlock new levels of speed.", "unlock-new-levels"),
    ("The possibilities are endless.", "possibilities-endless"),
    ("The best is yet to come.", "best-yet-to-come"),
    ("The results speak for themselves.", "speak-for-themselves"),
    ("We help teams stay ahead of the curve.", "ahead-of-the-curve"),
    ("Our commitment to excellence is clear.", "commitment-to-excellence"),
    ("Her care shines through in every chapter.", "shines-through"),
    ("We embark on this exciting journey together.", "embark-journey"),
])
def test_ai_tell_phrases_the_review_found(line, rule):
    assert any(item.rule_id == rule for item in hits(line + "\n", "ai-tell")), line


@pytest.mark.parametrize("line", [
    "We unlocked the door at noon.",
    "The data covers three weeks.",
    "The curve flattened after the fix.",
    "Sun came in through the window.",
])
def test_new_ai_tell_phrases_stay_quiet(line):
    assert hits(line + "\n", "ai-tell") == [], line


def test_overlapping_rules_count_one_tell_once():
    found = hits("In today's fast-paced world, teams wait.\n", "ai-tell")
    assert [item.rule_id for item in found] == ["in-todays-world"]
    assert found[0].match == "In today's fast-paced world"


def test_the_shorter_rule_still_fires_alone():
    found = hits("In today's fast-paced market, teams wait.\n", "ai-tell")
    assert [item.rule_id for item in found] == ["in-todays-fast-paced"]


def test_jargon_inside_a_pattern_is_not_counted_twice():
    found = hits("We harness the power of tests.\n")
    assert [(item.rule_id, item.category) for item in found] == [("harness-potential", "ai-tell")]


def test_jargon_outside_a_pattern_is_still_reported():
    found = hits("The harness the team runs is old.\n")
    assert any(item.category == "jargon" for item in found)


def test_different_categories_on_one_span_both_report():
    from slopcheck.check import drop_nested_findings
    from slopcheck.model import Finding

    def make(rule, category, column, end):
        return Finding("t.md", 1, column, 1, end, "error", category, rule, "x", "s")

    outer = make("a", "ai-tell", 1, 20)
    inner_same = make("b", "ai-tell", 3, 10)
    inner_other = make("c", "filler", 3, 10)
    kept = drop_nested_findings([outer, inner_same, inner_other], {"a", "b", "c"})
    assert kept == [outer, inner_other]


@pytest.mark.parametrize("line", [
    "We don't just ship code, we ship outcomes.",
    "It doesn't just run, it reports.",
])
def test_contrast_frame_flags_a_comma_join(line):
    assert hits(line + "\n", "contrast-frame"), line


@pytest.mark.parametrize("line", [
    "It doesn't only fail on Windows. It also fails on macOS.",
    "They don't only test it; they even fuzz it.",
    "We don't just test, we also lint, we ship.",
    "The cache isn't warm yet — it is still loading.",
    "They aren't cheap, they're also slow.",
])
def test_not_only_also_adds_a_claim_and_is_not_a_contrast_frame(line):
    assert hits(line + "\n", "contrast-frame") == [], line
