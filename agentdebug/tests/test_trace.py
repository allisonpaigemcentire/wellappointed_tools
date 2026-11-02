"""Trace summaries for the simple JSONL schema and OTel GenAI spans."""

import json
from pathlib import Path

from agentdebug.trace import (
    UnrecognizedTraceError,
    format_text,
    summarize_path,
    summarize_text,
)

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


# Regression cases from the 2026-11-02 review.


def test_otel_spans_are_read_in_start_time_order():
    summary = summarize_path(FIXTURES / "otel_unordered.json")
    assert [step.operation for step in summary.steps] == ["invoke_agent", "execute_tool", "execute_tool"]
    assert [step.tool_calls for step in summary.steps] == [[], ["lookup"], ["send"]]
    assert summary.first_error_step == 2
    assert summary.steps[1].error == "not_found"


def test_tool_spans_inherit_the_parent_agent():
    summary = summarize_path(FIXTURES / "otel_unordered.json")
    assert [step.agent for step in summary.steps] == ["shopper", "shopper", "shopper"]


def test_agent_is_inherited_through_an_unnamed_middle_span():
    spans = [
        {"spanId": "c", "parentSpanId": "b", "startTimeUnixNano": "3", "attributes": {"gen_ai.tool.name": "send"}},
        {"spanId": "b", "parentSpanId": "a", "startTimeUnixNano": "2", "attributes": {"gen_ai.operation.name": "chat"}},
        {"spanId": "a", "startTimeUnixNano": "1", "attributes": {"gen_ai.agent.name": "clerk"}},
    ]
    summary = summarize_text(json.dumps(spans))
    assert [step.agent for step in summary.steps] == ["clerk", "clerk", "clerk"]


def test_parent_cycle_does_not_hang():
    spans = [
        {"spanId": "a", "parentSpanId": "b", "attributes": {"gen_ai.tool.name": "x"}},
        {"spanId": "b", "parentSpanId": "a", "attributes": {"gen_ai.tool.name": "y"}},
    ]
    summary = summarize_text(json.dumps(spans))
    assert [step.agent for step in summary.steps] == ["", ""]


def test_spans_without_start_times_keep_file_order():
    spans = [
        {"spanId": "b", "startTimeUnixNano": "2", "attributes": {"gen_ai.tool.name": "second"}},
        {"spanId": "a", "attributes": {"gen_ai.tool.name": "first"}},
    ]
    summary = summarize_text(json.dumps(spans))
    assert [step.tool_calls for step in summary.steps] == [["second"], ["first"]]


def test_claude_code_session_reports_tools_and_the_tool_error():
    summary = summarize_path(FIXTURES / "claude_session.jsonl")
    assert len(summary.steps) == 5
    assert [step.operation for step in summary.steps] == ["user", "assistant", "tool_result", "assistant", "tool_result"]
    assert summary.steps[1].tool_calls == ["Bash"]
    assert summary.steps[1].tool_arguments == [{"command": "pytest"}]
    assert summary.first_error_step == 3
    assert summary.steps[2].error == "Bash: Error: exit 1 1 failed"
    assert summary.steps[3].agent == "claude-code:sidechain"
    assert summary.steps[4].error is None
    assert summary.input_tokens == 1200
    assert summary.output_tokens == 52


def test_unrecognized_trace_fails_instead_of_printing_empty_steps():
    lines = [json.dumps({"kind": "note", "body": "hello"}), json.dumps({"kind": "note", "body": "again"})]
    try:
        summarize_text("\n".join(lines))
    except UnrecognizedTraceError as exc:
        assert "no recognized fields" in str(exc)
        assert "Trace schema" in str(exc)
    else:
        raise AssertionError("expected UnrecognizedTraceError")


def test_repeat_needs_matching_tool_arguments():
    lines = [
        json.dumps({"agent": "w", "operation": "chat", "tool_calls": [{"name": "search", "arguments": {"q": "lamp"}}]}),
        json.dumps(
            {"agent": "w", "operation": "chat", "tool_calls": [{"name": "search", "arguments": {"q": "desk lamp brass"}}]}
        ),
    ]
    summary = summarize_text("\n".join(lines))
    assert summary.repeats == []
    assert summary.steps[1].tool_arguments == [{"q": "desk lamp brass"}]
    text = format_text(summary)
    assert 'args={"q":"desk lamp brass"}' in text
    same = summarize_text("\n".join([lines[0], lines[0]]))
    assert len(same.repeats) == 1


def test_json_string_arguments_are_parsed_and_long_args_are_shortened():
    long_value = "x" * 400
    summary = summarize_text(
        json.dumps({"agent": "w", "tool_calls": [{"name": "write", "arguments": json.dumps({"body": long_value})}]})
    )
    assert summary.steps[0].tool_arguments == [{"body": long_value}]
    text = format_text(summary)
    assert "see --format json" in text
    assert long_value not in text
    assert summary.to_dict()["steps"][0]["tool_arguments"] == [{"body": long_value}]


def test_name_of_a_tool_record_is_not_the_agent():
    summary = summarize_text(json.dumps({"type": "tool_call", "name": "search", "error": "timeout"}))
    assert summary.steps[0].agent == ""
    assert summary.steps[0].tool_calls == ["search"]
    both = summarize_text(json.dumps({"name": "search", "tool": "search"}))
    assert both.steps[0].agent == ""
    agent = summarize_text(json.dumps({"name": "planner", "operation": "chat", "tool_calls": ["search"]}))
    assert agent.steps[0].agent == "planner"


def _claude(kind, message=None, **extra):
    record = {"type": kind, "sessionId": "s1", "uuid": f"u-{kind}-{len(extra)}", **extra}
    if message is not None:
        record["message"] = message
    return json.dumps(record)


def test_claude_code_session_with_attachment_and_last_prompt_lines():
    lines = [
        json.dumps({"type": "queue-operation", "operation": "enqueue", "sessionId": "s1"}),
        _claude("user", {"role": "user", "content": "fix the test"}),
        _claude("attachment", attachment={"type": "file"}),
        _claude("attachment", attachment={"type": "file"}),
        _claude("future-line-type"),
        _claude(
            "assistant",
            {"id": "m1", "role": "assistant", "content": [{"type": "text", "text": "x"}], "usage": {}},
            error="authentication_failed",
            isApiErrorMessage=True,
        ),
        json.dumps({"type": "last-prompt", "lastPrompt": "fix the test", "sessionId": "s1"}),
    ]
    summary = summarize_text("\n".join(lines))
    assert [step.agent for step in summary.steps] == ["claude-code", "claude-code"]
    assert [step.operation for step in summary.steps] == ["user", "assistant"]
    assert summary.first_error_step == 2
    assert summary.steps[1].error == "api: authentication_failed"
    assert summary.repeats == []


def test_claude_code_content_block_lines_of_one_response_are_one_step():
    usage = {"input_tokens": 900, "output_tokens": 40}
    lines = [
        _claude("user", {"role": "user", "content": "run tests"}),
        _claude("assistant", {"id": "m1", "role": "assistant", "content": [{"type": "text", "text": "ok"}], "usage": usage}),
        _claude(
            "assistant",
            {
                "id": "m1",
                "role": "assistant",
                "content": [{"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "pytest"}}],
                "usage": usage,
            },
        ),
        _claude(
            "user",
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "is_error": True, "content": "exit 1"}]},
        ),
    ]
    summary = summarize_text("\n".join(lines))
    assert [step.operation for step in summary.steps] == ["user", "assistant", "tool_result"]
    assert summary.steps[1].tool_calls == ["Bash"]
    assert summary.steps[1].tool_arguments == [{"command": "pytest"}]
    assert summary.input_tokens == 900
    assert summary.output_tokens == 40
    assert summary.steps[2].error == "Bash: exit 1"
    assert summary.repeats == []


def test_single_agent_trace_with_only_token_counts_is_recognized():
    lines = [
        json.dumps({"step": 1, "operation": "chat", "input_tokens": 10, "output_tokens": 5}),
        json.dumps({"step": 2, "operation": "chat", "input_tokens": 12, "output_tokens": 7}),
    ]
    summary = summarize_text("\n".join(lines))
    assert summary.input_tokens == 22
    assert summary.output_tokens == 12


# Regression cases from the 2026-11-02 Debugging Bot review.


def _tool_result(tool_id, text, is_error=False):
    return _claude(
        "user",
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tool_id, "content": text, "is_error": is_error}]},
    )


def test_parallel_tool_results_are_one_step_not_a_repeat():
    lines = [
        _claude("user", {"role": "user", "content": "check both files"}),
        _claude(
            "assistant",
            {
                "id": "m1",
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "t1", "name": "Read", "input": {"file_path": "a.py"}},
                    {"type": "tool_use", "id": "t2", "name": "Read", "input": {"file_path": "b.py"}},
                ],
                "usage": {"input_tokens": 10, "output_tokens": 2},
            },
        ),
        _tool_result("t1", "ok"),
        _tool_result("t2", "No such file", is_error=True),
    ]
    summary = summarize_text("\n".join(lines))
    assert [step.operation for step in summary.steps] == ["user", "assistant", "tool_result"]
    assert summary.repeats == []
    assert summary.first_error_step == 3
    assert summary.steps[2].error == "Read: No such file"


def test_meta_user_lines_before_a_prompt_are_one_step():
    lines = [
        _claude("user", {"role": "user", "content": "<local-command-caveat>Caveat</local-command-caveat>"}, isMeta=True),
        _claude("user", {"role": "user", "content": "<command-name>/clear</command-name>"}),
        _claude("user", {"role": "user", "content": "<local-command-stdout></local-command-stdout>"}),
        _claude("user", {"role": "user", "content": "fix the test"}),
        _claude("assistant", {"id": "m1", "role": "assistant", "content": [{"type": "text", "text": "ok"}], "usage": {}}),
    ]
    summary = summarize_text("\n".join(lines))
    assert [step.operation for step in summary.steps] == ["user", "assistant"]
    assert summary.repeats == []


def test_trace_file_with_byte_order_mark(tmp_path: Path):
    path = tmp_path / "trace.jsonl"
    path.write_text(json.dumps({"agent": "a", "operation": "chat", "input_tokens": 3}) + "\n", encoding="utf-8-sig")
    assert summarize_path(path).steps[0].input_tokens == 3
