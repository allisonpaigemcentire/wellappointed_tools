"""The written method stays aligned with the template and the cited sources."""

from pathlib import Path

from agentdebug.report import template_text

ROOT = Path(__file__).resolve().parents[1]


def test_workflow_includes_the_template_body():
    workflow = (ROOT / "WORKFLOW.md").read_text(encoding="utf-8")
    body = template_text().split("\n", 1)[1]
    assert body.strip() in workflow


def test_playbook_cites_the_required_sources():
    text = (ROOT / "PLAYBOOK.md").read_text(encoding="utf-8")
    for needle in (
        "https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-spans/",
        "https://www.anthropic.com/engineering/built-multi-agent-research-system",
        "https://arxiv.org/abs/2503.13657",
        "https://hamel.dev/blog/posts/evals-faq/",
        "https://arxiv.org/abs/2406.12045",
        "https://arxiv.org/abs/2505.00212",
        "https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/",
        "specification and system design",
        "inter-agent misalignment",
        "task verification and termination",
        "pass^k",
        "pass@k",
        "53.5%",
        "14.2%",
        "first upstream failure",
        "N-1",
    ):
        assert needle.lower() in text.lower(), needle
