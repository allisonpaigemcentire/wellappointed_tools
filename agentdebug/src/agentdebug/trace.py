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

    def signature(self) -> tuple[str, str, tuple[str, ...]]:
        return (self.agent, self.operation, tuple(self.tool_calls))


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
    records = _load_records(text)
    steps = [_to_step(record, position) for position, record in enumerate(records, start=1)]
    return _summarize(steps)


def format_text(summary: TraceSummary) -> str:
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
        lines.append(
            f"step {step.index} agent={step.agent or '-'} operation={step.operation or '-'} "
            f"tools={tools} error={error} "
            f"input_tokens={_num(step.input_tokens)} output_tokens={_num(step.output_tokens)}"
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


def _to_step(record: dict[str, Any], position: int) -> StepView:
    if _looks_like_span(record):
        return _span_to_step(record, position)
    return _simple_to_step(record, position)


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
    index = record.get("step", record.get("index", position))
    if not isinstance(index, int):
        index = position
    agent = _first_str(record, "agent", "agent_name", "name") or ""
    operation = _first_str(record, "operation", "type", "role") or ""
    tools = _tool_names(record.get("tool_calls"))
    single = _first_str(record, "tool", "tool_name")
    if single and single not in tools:
        tools.append(single)
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
    )


def _span_to_step(record: dict[str, Any], position: int) -> StepView:
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
    tool_name = attrs.get("gen_ai.tool.name")
    if tool_name:
        tools.append(str(tool_name))
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
    )


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
    repeats: list[Repeat] = []
    index = 0
    while index < len(steps):
        signature = steps[index].signature()
        end = index + 1
        while end < len(steps) and steps[end].signature() == signature:
            end += 1
        length = end - index
        agent, operation, tools = signature
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
