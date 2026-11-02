"""Summarize a JSONL trace or an OpenTelemetry GenAI span export."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class StepView:
    index: int
    agent: str
    operation: str
    tool_calls: list[str] = field(default_factory=list)
    error: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    # One entry per tool call, in the same order: the call's arguments, or None.
    tool_arguments: list[Any] = field(default_factory=list)

    def signature(self) -> tuple[str, str, tuple[str, ...], tuple[str, ...]]:
        """Two steps repeat only when the agent, operation, tools, and tool arguments all match."""
        args = tuple(_canonical(value) for value in self.tool_arguments)
        return (self.agent, self.operation, tuple(self.tool_calls), args)

    def recognized(self) -> bool:
        """True when the step names an agent, a tool call, or an error, or carries token counts.

        A single-agent trace of `{"operation": "chat", "input_tokens": 10}` lines is valid
        and has no agent name, so token counts count as recognized fields too.
        """
        return bool(
            self.agent or self.tool_calls or self.error
            or self.input_tokens is not None or self.output_tokens is not None
        )


class UnrecognizedTraceError(ValueError):
    """The file parsed as JSON, but no step had an agent, a tool, an error, or token counts."""


@dataclass
class Repeat:
    start: int
    end: int
    agent: str
    operation: str
    tools: list[str]


@dataclass
class TraceSummary:
    steps: list[StepView]
    first_error_step: int | None
    repeats: list[Repeat]
    repeated_tools: list[dict[str, Any]]
    input_tokens: int
    output_tokens: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_count": len(self.steps),
            "first_error_step": self.first_error_step,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "repeats": [asdict(item) for item in self.repeats],
            "repeated_tools": self.repeated_tools,
            "steps": [asdict(step) for step in self.steps],
        }


def summarize_path(path: Path) -> TraceSummary:
    if not path.is_file():
        raise FileNotFoundError(path)
    text = path.read_text(encoding="utf-8")
    return summarize_text(text)


def summarize_text(text: str) -> TraceSummary:
    """Summarize a JSONL, OpenTelemetry, or Claude Code trace. Raises UnrecognizedTraceError when no step names an agent, a tool, an error, or token counts."""
    records = _load_records(text)
    if _is_claude_session(records):
        steps = _claude_code_steps(records)
    else:
        records = _order_spans(records)
        agents = _span_agents(records)
        steps = [_to_step(record, position, agents) for position, record in enumerate(records, start=1)]
    if steps and not any(step.recognized() for step in steps):
        raise UnrecognizedTraceError(
            f"no recognized fields in {len(steps)} records: no step has an agent, a tool call, an error, "
            "or token counts. "
            "See Trace schema in the agentdebug README for the accepted shapes."
        )
    return _summarize(steps)


def format_text(summary: TraceSummary) -> str:
    """Render a summary as plain text. Long tool arguments are cut, with a pointer to --format json."""
    lines = [
        f"steps: {len(summary.steps)}",
        f"first_error_step: {summary.first_error_step if summary.first_error_step is not None else '-'}",
        f"input_tokens: {summary.input_tokens}",
        f"output_tokens: {summary.output_tokens}",
        f"repeats: {len(summary.repeats)}",
        "",
    ]
    if not summary.steps:
        lines.append("(no steps)")
    for step in summary.steps:
        tools = ",".join(step.tool_calls) if step.tool_calls else "-"
        error = step.error if step.error else "-"
        args = _args_label(step)
        lines.append(
            f"step {step.index} agent={step.agent or '-'} operation={step.operation or '-'} "
            f"tools={tools} error={error} "
            f"input_tokens={_num(step.input_tokens)} output_tokens={_num(step.output_tokens)}"
            + (f" args={args}" if args else "")
        )
    if summary.repeats:
        lines.append("")
        lines.append("repeat ranges:")
        for item in summary.repeats:
            tools = ",".join(item.tools) if item.tools else "-"
            lines.append(
                f"- steps {item.start}-{item.end} agent={item.agent or '-'} "
                f"operation={item.operation or '-'} tools={tools}"
            )
    if summary.repeated_tools:
        lines.append("")
        lines.append("repeated tools:")
        for item in summary.repeated_tools:
            lines.append(f"- {item['name']} x{item['count']}")
    return "\n".join(lines) + "\n"


def _num(value: int | None) -> str:
    return "-" if value is None else str(value)


_ARGS_PREVIEW = 120


def _args_label(step: StepView) -> str:
    """Compact tool arguments for the text view. The JSON view keeps them whole."""
    if not any(value is not None for value in step.tool_arguments):
        return ""
    label = ";".join(_canonical(value) for value in step.tool_arguments)
    if len(label) > _ARGS_PREVIEW:
        cut = len(label) - _ARGS_PREVIEW
        label = label[:_ARGS_PREVIEW] + f"...(+{cut} chars, see --format json)"
    return label


def _canonical(value: Any) -> str:
    """A stable string for a value, so equal tool arguments compare equal."""
    if value is None:
        return "-"
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        return str(value)


def _load_records(text: str) -> list[dict[str, Any]]:
    stripped = text.strip()
    if not stripped:
        return []
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        data = None
    if data is not None:
        return _records_from_json(data)
    records: list[dict[str, Any]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        chunk = line.strip()
        if not chunk:
            continue
        try:
            item = json.loads(chunk)
        except json.JSONDecodeError as exc:
            raise ValueError(f"line {line_no} is not valid JSON: {exc.msg}") from exc
        if not isinstance(item, dict):
            raise ValueError(f"line {line_no} must be a JSON object")
        records.extend(_records_from_json(item))
    return records


def _records_from_json(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        records: list[dict[str, Any]] = []
        for index, item in enumerate(data, start=1):
            if not isinstance(item, dict):
                raise ValueError(f"item {index} must be a JSON object")
            records.extend(_records_from_json(item))
        return records
    if not isinstance(data, dict):
        raise ValueError("trace JSON must be an object, an array, or JSONL objects")
    if "resourceSpans" in data:
        return _otlp_spans(data)
    if "spans" in data and isinstance(data["spans"], list):
        return _records_from_json(data["spans"])
    return [data]


def _otlp_spans(payload: dict[str, Any]) -> list[dict[str, Any]]:
    spans: list[dict[str, Any]] = []
    for resource in payload.get("resourceSpans") or []:
        if not isinstance(resource, dict):
            continue
        scopes = resource.get("scopeSpans") or resource.get("instrumentationLibrarySpans") or []
        for scope in scopes:
            if not isinstance(scope, dict):
                continue
            for span in scope.get("spans") or []:
                if isinstance(span, dict):
                    spans.append(span)
    return spans


def _to_step(record: dict[str, Any], position: int, agents: dict[str, str] | None = None) -> StepView:
    """Turn one record into a step. A span with no agent takes the agent of its nearest ancestor."""
    if _looks_like_span(record):
        step = _span_to_step(record, position)
        if not step.agent and agents:
            step.agent = _inherited_agent(record, agents)
        return step
    return _simple_to_step(record, position)


_START_KEYS = ("startTimeUnixNano", "start_time_unix_nano", "startTimeUnixNanos")
_SPAN_ID_KEYS = ("spanId", "span_id")
_PARENT_ID_KEYS = ("parentSpanId", "parent_span_id", "parentId", "parent_id")


def _span_start(record: dict[str, Any]) -> int | None:
    """The span start time as an integer, or None when the span has none."""
    for key in _START_KEYS:
        if key in record:
            return _as_int(record[key])
    return None


def _order_spans(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Put OTel spans in start-time order. Exporters often write children before parents.

    The sort is stable, so spans with the same start keep file order. If any span has
    no start time, the file order is kept for the whole trace.
    """
    if not records or not all(_looks_like_span(record) for record in records):
        return records
    starts = [_span_start(record) for record in records]
    if any(start is None for start in starts):
        return records
    order = sorted(range(len(records)), key=lambda index: starts[index])
    return [records[index] for index in order]


def _span_id(record: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    """The first non-empty id found under the given keys."""
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _span_agents(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Map span id to (parent id, own agent name) so a tool span can inherit its agent."""
    tree: dict[str, Any] = {}
    for record in records:
        if not _looks_like_span(record):
            continue
        span_id = _span_id(record, _SPAN_ID_KEYS)
        if span_id is None:
            continue
        attrs = _flatten_attrs(record.get("attributes"))
        agent = record.get("gen_ai.agent.name") or attrs.get("gen_ai.agent.name") or attrs.get("gen_ai.agent.id")
        tree[span_id] = (_span_id(record, _PARENT_ID_KEYS), str(agent) if agent else "")
    return tree


def _inherited_agent(record: dict[str, Any], tree: dict[str, Any]) -> str:
    """Walk up parent span ids and return the first agent name found. Stops on a cycle."""
    parent = _span_id(record, _PARENT_ID_KEYS)
    seen: set[str] = set()
    while parent and parent in tree and parent not in seen:
        seen.add(parent)
        grandparent, agent = tree[parent]
        if agent:
            return agent
        parent = grandparent
    return ""


def _looks_like_span(record: dict[str, Any]) -> bool:
    """True for OTel spans. A simple step may still carry its own attributes bag."""
    if any(key in record for key in ("spanId", "traceId", "span_id", "trace_id")):
        return True
    if any(str(key).startswith("gen_ai.") for key in record):
        return True
    attrs = record.get("attributes")
    if isinstance(attrs, dict) and any(str(key).startswith("gen_ai.") for key in attrs):
        return True
    if isinstance(attrs, list):
        return any(
            isinstance(item, dict) and str(item.get("key", "")).startswith("gen_ai.")
            for item in attrs
        )
    return False


def _simple_to_step(record: dict[str, Any], position: int) -> StepView:
    """Turn a flat JSONL record into a step."""
    index = record.get("step", record.get("index", position))
    if not isinstance(index, int):
        index = position
    operation = _first_str(record, "operation", "type", "role") or ""
    tools = _tool_names(record.get("tool_calls"))
    arguments = _tool_arguments(record.get("tool_calls"))
    single = _first_str(record, "tool", "tool_name")
    agent = _first_str(record, "agent", "agent_name") or ""
    name = _first_str(record, "name")
    if name and not agent:
        # A record such as {"type": "tool_call", "name": "search"} names a tool, not an agent.
        if single is None and not tools and "tool" in operation.lower():
            single = name
        elif single is None or single != name:
            agent = name
    if single and single not in tools:
        tools.append(single)
        arguments.append(record.get("arguments", record.get("args", record.get("input"))))
    error = _clean_error(record.get("error"))
    if error is None:
        for tool in record.get("tool_calls") or []:
            if isinstance(tool, dict):
                tool_error = _clean_error(tool.get("error"))
                if tool_error:
                    tool_name = str(tool.get("name") or tool.get("tool") or "tool")
                    error = f"{tool_name}: {tool_error}"
                    break
    input_tokens, output_tokens = _simple_tokens(record)
    return StepView(
        index=index,
        agent=agent,
        operation=operation,
        tool_calls=tools,
        error=error,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        tool_arguments=arguments if any(value is not None for value in arguments) else [],
    )


def _tool_arguments(value: Any) -> list[Any]:
    """Arguments for each named entry in tool_calls, matching _tool_names order."""
    if not isinstance(value, list):
        return []
    found: list[Any] = []
    for item in value:
        if isinstance(item, str) and item:
            found.append(None)
        elif isinstance(item, dict) and (item.get("name") or item.get("tool") or item.get("tool_name")):
            raw = item.get("arguments", item.get("args", item.get("input")))
            found.append(_parse_json_string(raw))
    return found


def _span_to_step(record: dict[str, Any], position: int) -> StepView:
    """Turn an OpenTelemetry span into a step, reading the GenAI attributes."""
    attrs = _flatten_attrs(record.get("attributes"))
    for key in ("gen_ai.operation.name", "gen_ai.agent.name", "gen_ai.tool.name", "gen_ai.usage.input_tokens"):
        if key in record and key not in attrs:
            attrs[key] = record[key]
    agent = str(
        attrs.get("gen_ai.agent.name")
        or attrs.get("gen_ai.agent.id")
        or ""
    )
    operation = str(attrs.get("gen_ai.operation.name") or record.get("name") or "")
    tools: list[str] = []
    arguments: list[Any] = []
    tool_name = attrs.get("gen_ai.tool.name")
    if tool_name:
        tools.append(str(tool_name))
        arguments.append(_parse_json_string(attrs.get("gen_ai.tool.call.arguments")))
    for event in record.get("events") or []:
        if not isinstance(event, dict):
            continue
        event_attrs = _flatten_attrs(event.get("attributes"))
        event_tool = event_attrs.get("gen_ai.tool.name")
        event_name = str(event.get("name") or "")
        if event_tool:
            label = str(event_tool)
        elif "tool" in event_name:
            label = event_name
        else:
            continue
        if label not in tools:
            tools.append(label)
            arguments.append(_parse_json_string(event_attrs.get("gen_ai.tool.call.arguments")))
    error = _span_error(record, attrs)
    input_tokens = _as_int(
        attrs.get("gen_ai.usage.input_tokens", attrs.get("gen_ai.usage.prompt_tokens"))
    )
    output_tokens = _as_int(
        attrs.get("gen_ai.usage.output_tokens", attrs.get("gen_ai.usage.completion_tokens"))
    )
    return StepView(
        index=position,
        agent=agent,
        operation=operation,
        tool_calls=tools,
        error=error,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        tool_arguments=arguments if any(value is not None for value in arguments) else [],
    )


def _parse_json_string(value: Any) -> Any:
    """Parse a JSON string, or return the value unchanged."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _span_error(record: dict[str, Any], attrs: dict[str, Any]) -> str | None:
    status = record.get("status") or {}
    if not isinstance(status, dict):
        status = {}
    code = status.get("code", status.get("status_code"))
    message = status.get("message") or status.get("description")
    error_type = attrs.get("error.type") or attrs.get("exception.type")
    if not _is_error_code(code) and not error_type:
        return None
    text = message or error_type or "error"
    return str(text)


def _is_error_code(code: Any) -> bool:
    if code is None or isinstance(code, bool):
        return False
    if isinstance(code, int):
        return code == 2
    return str(code).upper() in {"ERROR", "STATUS_CODE_ERROR", "2"}


def _simple_tokens(record: dict[str, Any]) -> tuple[int | None, int | None]:
    tokens = record.get("tokens")
    usage = record.get("usage") if isinstance(record.get("usage"), dict) else {}
    token_map = tokens if isinstance(tokens, dict) else {}
    input_tokens = _as_int(
        token_map.get("input", token_map.get("prompt", record.get("input_tokens", usage.get("prompt_tokens", usage.get("input_tokens")))))
    )
    output_tokens = _as_int(
        token_map.get("output", token_map.get("completion", record.get("output_tokens", usage.get("completion_tokens", usage.get("output_tokens")))))
    )
    return input_tokens, output_tokens


def _tool_names(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    names: list[str] = []
    for item in value:
        if isinstance(item, str) and item:
            names.append(item)
        elif isinstance(item, dict):
            name = item.get("name") or item.get("tool") or item.get("tool_name")
            if name:
                names.append(str(name))
    return names


def _flatten_attrs(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if not isinstance(value, list):
        return {}
    flat: dict[str, Any] = {}
    for item in value:
        if not isinstance(item, dict) or "key" not in item:
            continue
        raw = item.get("value")
        flat[str(item["key"])] = _otlp_value(raw)
    return flat


def _otlp_value(raw: Any) -> Any:
    if not isinstance(raw, dict):
        return raw
    for key in ("stringValue", "intValue", "doubleValue", "boolValue"):
        if key in raw:
            if key == "intValue":
                return _as_int(raw[key])
            return raw[key]
    return raw


_CLAUDE_TYPES = {"user", "assistant", "system"}
_CLAUDE_TURN_TYPES = {"user", "assistant"}
_CLAUDE_META_TYPES = {"summary", "file-history-snapshot", "queue-operation", "attachment", "last-prompt"}
_CLAUDE_SESSION_KEYS = ("sessionId", "uuid", "leafUuid")


def _is_claude_meta(record: dict[str, Any]) -> bool:
    """True for Claude Code records that carry no turn, such as a summary line."""
    return record.get("type") in _CLAUDE_META_TYPES


def _is_claude_session(records: list[dict[str, Any]]) -> bool:
    """True when the file is a Claude Code session.

    At least one line is a user or assistant turn, and every line carries a
    Claude Code session key or a known non-turn type. Claude Code adds new
    non-turn line types over time (attachment and last-prompt are recent),
    so an unknown type with a session id does not send the file down the
    generic path.
    """
    if not any(_looks_like_claude_code(record) for record in records):
        return False
    return all(
        _is_claude_meta(record) or any(key in record for key in _CLAUDE_SESSION_KEYS)
        for record in records
    )


def _looks_like_claude_code(record: dict[str, Any]) -> bool:
    """A Claude Code session line: {"type": "user"|"assistant", "message": {...}, "uuid": ...}."""
    if record.get("type") not in _CLAUDE_TYPES:
        return False
    if "uuid" not in record and "sessionId" not in record:
        return False
    return record.get("type") == "system" or isinstance(record.get("message"), dict)


def _claude_code_steps(records: list[dict[str, Any]]) -> list[StepView]:
    """Steps from a Claude Code session JSONL (~/.claude/projects/<project>/<session>.jsonl).

    Each user or assistant line is a step. tool_use blocks become tool calls with their
    input as arguments. A tool_result with is_error true is reported as `tool: message`
    on the step that carries the result.
    """
    tool_names: dict[str, str] = {}
    steps: list[StepView] = []
    last_message_id: str | None = None
    for record in records:
        if record.get("type") not in _CLAUDE_TURN_TYPES:
            last_message_id = None
            continue
        raw_message = record.get("message")
        message: dict[str, Any] = raw_message if isinstance(raw_message, dict) else {}
        role = str(message.get("role") or record.get("type") or "")
        agent = "claude-code:sidechain" if record.get("isSidechain") else "claude-code"
        content = message.get("content")
        blocks = content if isinstance(content, list) else []
        tools: list[str] = []
        arguments: list[Any] = []
        error: str | None = None
        results = 0
        for block in blocks:
            if not isinstance(block, dict):
                continue
            kind = block.get("type")
            if kind == "tool_use":
                name = str(block.get("name") or "tool")
                tools.append(name)
                arguments.append(block.get("input"))
                if isinstance(block.get("id"), str):
                    tool_names[block["id"]] = name
            elif kind == "tool_result":
                results += 1
                if block.get("is_error") and error is None:
                    name = tool_names.get(str(block.get("tool_use_id")), "tool")
                    error = f"{name}: {_result_text(block.get('content')) or 'error'}"
        if error is None and role == "assistant" and (record.get("isApiErrorMessage") or record.get("error")):
            # A failed model call: Claude Code writes {"error": "authentication_failed", "isApiErrorMessage": true}.
            error = f"api: {_clean_error(record.get('error')) or 'error'}"
        raw_usage = message.get("usage")
        usage: dict[str, Any] = raw_usage if isinstance(raw_usage, dict) else {}
        operation = "tool_result" if results and role == "user" else role
        message_id = message.get("id") if role == "assistant" and isinstance(message.get("id"), str) else None
        if message_id and message_id == last_message_id and steps:
            # Claude Code writes one line per content block of a single response, each
            # with the same message id and the same usage. Fold them into one step so
            # tokens are counted once and text, then tool_use, is not a "repeat".
            _merge_claude_step(steps[-1], tools, arguments, error, usage)
            continue
        last_message_id = message_id
        steps.append(
            StepView(
                index=len(steps) + 1,
                agent=agent,
                operation=operation,
                tool_calls=tools,
                error=error,
                input_tokens=_as_int(usage.get("input_tokens")),
                output_tokens=_as_int(usage.get("output_tokens")),
                tool_arguments=arguments if any(value is not None for value in arguments) else [],
            )
        )
    return steps


def _merge_claude_step(
    step: StepView,
    tools: list[str],
    arguments: list[Any],
    error: str | None,
    usage: dict[str, Any],
) -> None:
    """Add one more content-block line of the same assistant response to its step."""
    merged_args = (step.tool_arguments or [None] * len(step.tool_calls)) + arguments
    step.tool_calls = step.tool_calls + tools
    step.tool_arguments = merged_args if any(value is not None for value in merged_args) else []
    step.error = step.error or error
    # The usage on each line is the response's usage, not a delta. Keep the last one.
    if _as_int(usage.get("input_tokens")) is not None:
        step.input_tokens = _as_int(usage.get("input_tokens"))
    if _as_int(usage.get("output_tokens")) is not None:
        step.output_tokens = _as_int(usage.get("output_tokens"))


def _result_text(content: Any) -> str:
    """The text of a Claude Code tool result, on one line and cut to 200 characters."""
    if isinstance(content, str):
        return " ".join(content.split())[:200]
    if isinstance(content, list):
        parts = [
            str(block.get("text"))
            for block in content
            if isinstance(block, dict) and block.get("type") == "text" and block.get("text")
        ]
        return " ".join(" ".join(parts).split())[:200]
    return ""


def _summarize(steps: list[StepView]) -> TraceSummary:
    first_error = next((step.index for step in steps if step.error), None)
    repeats = _consecutive_repeats(steps)
    counts: dict[str, int] = {}
    for step in steps:
        for name in step.tool_calls:
            counts[name] = counts.get(name, 0) + 1
    repeated = [
        {"name": name, "count": count}
        for name, count in sorted(counts.items())
        if count >= 3
    ]
    input_total = sum(step.input_tokens or 0 for step in steps)
    output_total = sum(step.output_tokens or 0 for step in steps)
    return TraceSummary(
        steps=steps,
        first_error_step=first_error,
        repeats=repeats,
        repeated_tools=repeated,
        input_tokens=input_total,
        output_tokens=output_total,
    )


def _consecutive_repeats(steps: list[StepView]) -> list[Repeat]:
    """Runs of back-to-back steps with the same agent, operation, tools, and arguments."""
    repeats: list[Repeat] = []
    index = 0
    while index < len(steps):
        signature = steps[index].signature()
        end = index + 1
        while end < len(steps) and steps[end].signature() == signature:
            end += 1
        length = end - index
        agent, operation, tools, _args = signature
        meaningful = bool(agent or operation or tools)
        if length >= 2 and meaningful:
            repeats.append(
                Repeat(
                    start=steps[index].index,
                    end=steps[end - 1].index,
                    agent=agent,
                    operation=operation,
                    tools=list(tools),
                )
            )
            index = end
        else:
            index += 1
    return repeats


def _first_str(record: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _clean_error(value: Any) -> str | None:
    if value is None or value is False:
        return None
    if value is True:
        return "error"
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, dict):
        for key in ("message", "type", "error"):
            text = value.get(key)
            if isinstance(text, str) and text.strip():
                return text.strip()
        return "error"
    return str(value)


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None
