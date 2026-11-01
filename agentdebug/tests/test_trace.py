"""Trace summaries for the simple JSONL schema and OTel GenAI spans."""

import json
from pathlib import Path

from agentdebug.trace import format_text, summarize_path, summarize_text

FIXTURES = Path(__file__).parent / "fixtures"


def test_jsonl_reports_first_error_tokens_and_repeat():
    summary = summarize_path(FIXTURES / "trace.jsonl")
    assert summary.first_error_step == 2
    assert [step.agent for step in summary.steps] == ["planner", "planner", "writer"]
    assert summary.steps[0].tool_calls == ["search"]
    assert summary.steps[1].error == "timeout"
    assert summary.input_tokens == 29
    assert summary.output_tokens == 24
    assert len(summary.repeats) == 1
    assert (summary.repeats[0].start, summary.repeats[0].end) == (1, 2)
    text = format_text(summary)
    assert "first_error_step: 2" in text
    assert "step 2 agent=planner" in text
    assert "steps 1-2" in text


def test_otel_spans_and_attribute_lists():
    summary = summarize_path(FIXTURES / "otel_spans.json")
    assert len(summary.steps) == 2
    assert summary.steps[0].agent == "researcher"
    assert summary.steps[0].operation == "chat"
    assert summary.steps[0].tool_calls == ["lookup"]
    assert summary.steps[0].input_tokens == 15
    assert summary.steps[0].error is None
    assert summary.steps[1].error == "deadline exceeded"
    assert summary.steps[1].input_tokens == 3
    assert summary.first_error_step == 2


def test_otlp_resource_spans_and_tool_error():
    payload = {
        "resourceSpans": [
            {
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "name": "chat",
                                "attributes": [
                                    {"key": "gen_ai.agent.name", "value": {"stringValue": "clerk"}},
                                    {"key": "gen_ai.operation.name", "value": {"stringValue": "chat"}},
                                    {"key": "gen_ai.usage.output_tokens", "value": {"intValue": 4}},
                                ],
                                "status": {"code": 1},
                            }
                        ]
                    }
                ]
            }
        ]
    }
    summary = summarize_text(json.dumps(payload))
    assert summary.steps[0].agent == "clerk"
    assert summary.steps[0].output_tokens == 4
    assert summary.first_error_step is None

    tool_error = summarize_text(
        json.dumps(
            {
                "step": 4,
                "agent": "clerk",
                "tool_calls": [{"name": "lookup", "error": "empty payload"}],
            }
        )
    )
    assert tool_error.first_error_step == 4
    assert tool_error.steps[0].error == "lookup: empty payload"


def test_repeated_tool_across_nonconsecutive_steps():
    lines = []
    for step, agent in ((1, "a"), (2, "b"), (3, "a")):
        lines.append(
            json.dumps(
                {
                    "step": step,
                    "agent": agent,
                    "operation": "chat",
                    "tool_calls": ["search"],
                }
            )
        )
    summary = summarize_text("\n".join(lines))
    assert summary.repeats == []
    assert summary.repeated_tools == [{"name": "search", "count": 3}]


def test_empty_file_and_invalid_line(tmp_path: Path):
    empty = tmp_path / "empty.jsonl"
    empty.write_text("\n\n", encoding="utf-8")
    summary = summarize_path(empty)
    assert summary.steps == []
    assert "no steps" in format_text(summary)
    broken = tmp_path / "broken.jsonl"
    broken.write_text("{not json}\n", encoding="utf-8")
    try:
        summarize_path(broken)
    except ValueError as exc:
        assert "line 1" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_simple_step_may_carry_a_non_otel_attribute_bag():
    summary = summarize_text(
        json.dumps(
            {
                "step": 1,
                "agent": "planner",
                "operation": "chat",
                "attributes": {"sku": "DL-14"},
                "tokens": {"input": 2, "output": 3},
            }
        )
    )
    assert summary.steps[0].agent == "planner"
    assert summary.steps[0].operation == "chat"
    assert summary.input_tokens == 2


def test_usage_object_tokens():
    summary = summarize_text(
        json.dumps({"agent": "writer", "usage": {"prompt_tokens": 5, "completion_tokens": 6}})
    )
    assert summary.input_tokens == 5
    assert summary.output_tokens == 6
