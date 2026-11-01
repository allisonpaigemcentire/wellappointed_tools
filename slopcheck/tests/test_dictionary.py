"""The shipped dictionary matches the four-bucket source, with private notes removed."""

from pathlib import Path

from slopcheck.load import load_jargon, packaged_text

ENTRIES = load_jargon()
BY = {entry["term"]: entry for entry in ENTRIES}
RAW = packaged_text("jargon.yaml")


def test_bucket_counts():
    buckets = {}
    for entry in ENTRIES:
        buckets[entry["bucket"]] = buckets.get(entry["bucket"], 0) + 1
    assert buckets == {"keep": 6, "define": 47, "replace": 10, "cut": 5}
    assert len(ENTRIES) == 68


def test_required_placements_and_translations():
    expect = {
        "agentic": "replace",
        "inference": "replace",
        "few-shot / in-context learning": "replace",
        "guardrails": "replace",
        "human-in-the-loop": "replace",
        "grounding": "replace",
        "AI-native / AI-first": "cut",
        "AI-enabled": "cut",
        "frontier model": "cut",
        "AGI": "cut",
        "10x / game-changer / supercharge": "cut",
        "evals": "define",
        "multi-agent": "define",
        "embeddings": "define",
        "prompt": "keep",
        "workflow (vs. agent)": "define",
        "agent washing": "define",
        "system prompt": "define",
        "orchestration": "define",
        "temperature": "define",
        "subagent": "define",
        "computer use": "define",
        "chain-of-thought": "define",
        "distillation": "define",
        "synthetic data": "define",
        "vibe coding": "define",
        "prompt injection": "define",
        "open-weight": "define",
        "LLM-as-judge": "define",
        "RAG": "define",
        "context window": "define",
        "context engineering": "define",
        "tokens": "define",
        "hallucination": "define",
        "agent": "define",
    }
    for term, bucket in expect.items():
        assert BY[term]["bucket"] == bucket, term
    assert BY["evals"]["plain"] == "a fixed set of test cases rerun after every change and scored"
    assert BY["inference"]["plain"] == "running the model"
    assert BY["agentic"]["plain"] == "say what it does"
    assert BY["embeddings"]["plain"] == "coordinates where similar meanings land near each other"
    assert "fingerprint" not in str(BY["embeddings"])
    assert "agent" not in BY["multi-agent"]["plain"].lower()


def test_false_friends():
    required = {
        "agent",
        "harness / scaffold",
        "grounding",
        "tokens",
        "temperature",
        "memory",
        "reasoning model",
        "hallucination",
        "computer use",
        "distillation",
        "time horizon",
        "workflow (vs. agent)",
    }
    flagged = {entry["term"] for entry in ENTRIES if entry["false_friend"]}
    assert required <= flagged
    assert all(BY[term]["bucket"] != "keep" for term in flagged)


def test_every_entry_compiles_and_has_no_em_dash():
    assert "\u2014" not in RAW
    for entry in ENTRIES:
        assert entry["plain"]
        assert entry["rx"]
        assert isinstance(entry["false_friend"], bool)


def test_private_notes_are_gone():
    # Stand-ins for notes that used to name a private project. Those names are
    # not part of this package. Merriam, WordNet, and the file markers below
    # are dictionary-hygiene checks, not project names.
    for token in (
        "Jordan Hale",
        "zz-private-notebook-token",
        "Merriam",
        "WordNet",
        "etymolog",
        "banned-phrases",
        "src-",
    ):
        assert token not in RAW, token


def test_shipped_rules_file_lives_next_to_the_dictionary():
    root = Path(__file__).resolve().parents[1]
    assert (root / "src" / "slopcheck" / "data" / "rules.yaml").is_file()
    assert (root / "src" / "slopcheck" / "data" / "jargon.yaml").is_file()
