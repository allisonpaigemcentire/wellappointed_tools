# agentdebug

A dependency-light toolkit for finding bugs in agentic and multi-agent systems. The method is in [PLAYBOOK.md](PLAYBOOK.md). A review you can follow on your own repository is in [WORKFLOW.md](WORKFLOW.md). The CLI scaffolds the report, scans Python for a few recurring smells, and summarizes a trace. It does not decide root cause. Read the trace.

The runtime code uses the Python standard library. Tests use pytest.

## Install

From this directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

You can also skip the install and run from a checkout:

```bash
PYTHONPATH=src python3 -m agentdebug --help
```

The console script `agentdebug` is available after `pip install -e .`.

## Report scaffold

```bash
agentdebug report init "desk lamp checkout"
```

That writes `Desk-lamp-checkout.md` in the current directory, from [the review template](src/agentdebug/templates/review_report.md). It will not overwrite an existing file unless you pass `--force`. `--out path.md` chooses the path.

## Lint

```bash
agentdebug lint path/to/package
agentdebug lint path/to/one_file.py --format json
```

The text report is `file:line`, a rule id, a message, and a hint. JSON is a list of objects with `path`, `line`, `rule_id`, `message`, and `hint`. The process exits `1` when there is at least one finding, and `0` when there are none.

These are smells, not proofs. A capped loop whose limit lives in a config file this scanner does not see will be flagged if the cap is not visible in the `while` body.

| Rule | Smell |
|---|---|
| `AGT001` | Bare `except`, or an `except` whose body is only `pass` |
| `AGT002` | A check or gate that returns `True` on every path, or a result hard-coded as passed with empty findings |
| `AGT003` | `while True` around a model or tool call with no max-iteration cap |
| `AGT004` | A retry loop or `@retry` with no stop or attempt limit |
| `AGT005` | A prefix slice such as `prompt[:N]` or `text[:N]` on a prompt or model input |
| `AGT006` | An HTTP or model client call with no `timeout` |
| `AGT007` | A tool that writes or sends and has no approval parameter |
| `AGT008` | A string literal that looks like a committed secret |

`AGT000` means the file could not be decoded or parsed, so the other rules did not run.

Try it on the fixtures:

```bash
PYTHONPATH=src python3 -m agentdebug lint tests/fixtures/smells.py
PYTHONPATH=src python3 -m agentdebug lint tests/fixtures/clean.py
```

The first exits `1`. The second prints `no findings` and exits `0`.

## Trace summary

```bash
agentdebug trace summarize trace.jsonl
agentdebug trace summarize spans.json --format json
```

The text report lists, per step, the agent, the operation, tool calls, the error, and token counts. It also prints consecutive repeated steps, tools that appear at least three times, and the first step that carries an error. That step is the first recorded error, which you still have to check against the playbook's "first upstream failure" rule. The command exits `2` if the file cannot be parsed, or if it parses but no step has an agent, a tool call, an error, or token counts. That second case usually means the file is in a shape this command does not read, and an empty summary would hide the errors in it. A trace that contains errors still exits `0`; the errors are the content of the summary.

Two steps count as a repeat only when the agent, operation, tool names, and tool arguments all match, so `search(q=lamp)` followed by `search(q=desk lamp brass)` is not a repeat. The text view prints each step's tool arguments after `args=`, shortened to 120 characters. The JSON view has them whole in `tool_arguments`. Tool outputs are not in the summary.

### Trace schema

Three shapes are accepted.

**Simple JSONL.** One JSON object per line (a JSON array of those objects works too):

```json
{
  "step": 1,
  "agent": "planner",
  "operation": "chat",
  "tool_calls": [{"name": "search", "arguments": {"q": "desk lamp"}}],
  "error": null,
  "tokens": {"input": 10, "output": 4}
}
```

`tokens` may instead be `input_tokens` and `output_tokens`, or a `usage` object with `prompt_tokens` and `completion_tokens`. `error` may be a string. An error on a tool call object is reported as `tool-name: message`. `step` is optional; lines are numbered in order when it is missing. `name` is read as the agent, unless the record also names that tool or its `operation` or `type` mentions a tool, as in `{"type": "tool_call", "name": "search"}`. Then `name` is the tool.

**OpenTelemetry GenAI spans.** A JSON array of span objects, or an OTLP `resourceSpans` document. Attributes may be a map or the OTLP list of `{key, value}` pairs. The summarizer reads `gen_ai.agent.name`, `gen_ai.operation.name`, `gen_ai.tool.name`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `error.type`, span status, and tool events, and `gen_ai.tool.call.arguments`. Spans are put in `startTimeUnixNano` order, because exporters often write a child before its parent. If any span has no start time, file order is kept. A span with no agent name takes it from the nearest ancestor through `parentSpanId`. See the [GenAI span conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-spans/).

**Claude Code session JSONL.** The files under `~/.claude/projects/<project>/`. Each `user` or `assistant` line is a step, with agent `claude-code` (or `claude-code:sidechain` for a subagent line). `tool_use` blocks are tool calls, with their `input` as arguments, and a `tool_result` with `is_error: true` is the step's error, reported as `tool-name: message`. `summary`, snapshot, `attachment`, `last-prompt`, and other non-turn lines are skipped. Lines that share one assistant `message.id` (Claude Code writes one line per content block of a response) are one step, with its usage counted once. A failed model call (`"isApiErrorMessage": true`) is the step's error, reported as `api: message`. `input_tokens` is the message's `usage.input_tokens`, which leaves out `cache_read_input_tokens` and `cache_creation_input_tokens`, so on a cached session it reads far lower than the context the model saw. The format is not a published schema, so a future Claude Code release may change it. Cursor and Gemini CLI transcripts are not read yet.

```bash
PYTHONPATH=src python3 -m agentdebug trace summarize tests/fixtures/trace.jsonl
PYTHONPATH=src python3 -m agentdebug trace summarize tests/fixtures/otel_spans.json --format json
```

## Tests

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT. The license for this repository is [LICENSE](../LICENSE) at the repository root.
