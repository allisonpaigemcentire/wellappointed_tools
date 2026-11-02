"""Unfamiliar-word suggestions, with and without wordfreq."""

from slopcheck.load import load_jargon
from slopcheck.suggest import SuggestError, suggest_terms, zipf_frequency

JARGON = load_jargon()


def test_suggest_uses_the_injected_score_and_skips_dictionary_words():
    text = "The prompt used a xyzzyplugh in the RAG pipeline.\n"
    scores = {"xyzzyplugh": 1.2, "prompt": 4.0, "pipeline": 4.0, "used": 5.0, "the": 7.0}

    def freq(word: str) -> float:
        return scores.get(word, 4.5)

    found = suggest_terms(text, JARGON, zipf_below=3, frequency=freq)
    terms = [item.term for item in found]
    assert terms == ["xyzzyplugh"]
    assert found[0].line == 1
    assert found[0].zipf == 1.2


def test_suggest_ignores_code_fences():
    text = "```\nxyzzyplugh\n```\nThe sentence is ordinary.\n"

    def freq(word: str) -> float:
        return 0.5 if word == "xyzzyplugh" else 5.0

    assert suggest_terms(text, JARGON, frequency=freq) == []


def test_zipf_helper_imports_or_explains():
    try:
        score = zipf_frequency("the")
    except SuggestError as exc:
        assert "wordfreq" in str(exc)
        return
    assert score > 3


def test_cli_suggest_failure_is_exit_2(tmp_path, monkeypatch, capsys):
    from slopcheck.cli import main

    path = tmp_path / "note.md"
    path.write_text("Hello from the team.\n", encoding="utf-8")

    def boom(*_args, **_kwargs):
        raise SuggestError('The term suggester needs wordfreq. Install it with: pip install "wordfreq>=3.1"')

    monkeypatch.setattr("slopcheck.cli.suggest_terms", boom)
    assert main(["--suggest-terms", str(path)]) == 2
    assert "suggest" in capsys.readouterr().err
