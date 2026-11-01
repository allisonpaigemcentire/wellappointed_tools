# Playbook: finding bugs in agentic systems

This is a method for debugging one agent or a group of agents that call tools. The failure you can see, a bad paragraph or a stuck loop, is often a later symptom. The work is to name the earliest break, reproduce it in a small way, and lock the fix with a test that checks a tool call or the final state.

`agentdebug lint` and `agentdebug trace summarize` are hints. They do not decide the cause. Read the trace.

## 1. Trace the run

Record one span per model call and one span per tool call, parented under the agent that made them. Use the [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-spans/) so traces from different frameworks can be compared. Agent and tool spans are specified alongside those conventions in the [GenAI agent span notes](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-agent-spans.md).

On each span, keep the attributes that a later review can actually use:

| Attribute | What to put there |
|---|---|
| `gen_ai.operation.name` | `chat`, `execute_tool`, or the other operation name from the spec |
| `gen_ai.agent.name` | Which agent took the step |
| `gen_ai.request.model` | Model id |
| `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens` | Token counts |
| `gen_ai.tool.name` | Tool that was called, on tool spans and on events such as `gen_ai.tool.call` |
| `error.type` | Stable error class when the step failed (`timeout`, `not_found`, ...) |

Also record the sampling seed and the temperature, on the span or beside it. Replay depends on both. Content capture is opt-in in the spec: do not copy secrets, credentials, or private documents into span attributes. A pointer to an access-controlled blob is enough.

If you do not have an OpenTelemetry export yet, a JSONL file with one object per step is enough to start. `agentdebug trace summarize` accepts both shapes. The field list is in the [README](README.md#trace-schema).

## 2. Code the errors, and keep only the first upstream failure

Read traces before you pick a taxonomy.

**Open coding.** For each failed trace, write a short label in your own words for what went wrong. Stay concrete: "tool result was cut at 500 characters", "writer never saw the price unit". Do this without a checklist, or the checklist becomes the only bugs you can see.

**Axial coding.** After a batch of labels, group the ones that are the same kind of break. Those groups are the axes you will count.

**First upstream failure only.** Each trace gets one cause label: the earliest step that made the later steps unable to succeed. If the extractor dropped the unit, and the writer then apologized with the wrong total, the cause is the extractor. The apology is a symptom. Counting both inflates the writer and hides the break you can fix.

This is the same discipline as an error analysis pass: separate labels, then cluster them, and do not let a fluent final message talk you out of the earlier step. The [evals FAQ](https://hamel.dev/blog/posts/evals-faq/) is the practical reference for that pass, including why binary labels beat a 1–5 scale while you are still learning what "bad" means.

## 3. Shrink to a minimal repro, then replay N-1

A failing production trace is a terrible test. Shrink it until removing anything else makes the failure disappear:

- fewer turns
- fewer tools
- a shorter input that still contains the one fact the bug depends on
- recorded tool outputs instead of live network calls

Then do an **N-1 replay**. Take the recorded prefix, drop the last turn, and run again with the recorded seed, temperature, and tool outputs. If the outcome is already wrong, the last turn did not introduce the bug. If the outcome is fine, the last turn is part of the repro and you keep it. Repeat while the failure still shows. The thing you have left is the regression fixture.

## 4. Build a transition failure matrix

Once each trace has a single first-upstream label, count the handoffs:

| From step | To step | Failure | Count |
|---|---|---|---|
| planner tool call | price lookup | result unit does not match the tool description | 4 |
| price lookup | writer | writer totals the truncated number | 4 |

Rows are the step that handed work off. Columns are the failure observed at the next step. A dense cell is where to spend the fix. Do not put downstream symptoms in as extra rows for the same trace.

## 5. Put the labels on the MAST categories

After the open-coding labels exist, map each first-upstream failure onto [MAST](https://arxiv.org/abs/2503.13657) (Why Do Multi-Agent LLM Systems Fail?, arXiv:2503.13657). The taxonomy has fourteen modes in three categories. Use the category as a column in the matrix. Keep your own label when none of the modes fit. The category is not a substitute for `file:line` evidence.

1. **System design issues (FC1).** This is the specification and system design bucket. The task spec, the role spec, or the architecture was wrong or was not followed: disobeying the task specification, disobeying the role specification, repeating a step, losing conversation history, or not knowing the termination condition.
2. **Inter-agent misalignment (FC2).** Agents did not share what the next agent needed: a conversation reset, failing to ask for clarification, task derailment, withholding information, ignoring another agent's input, or a mismatch between the reasoning and the action.
3. **Task verification (FC3).** This is the task verification and termination bucket. The system stopped too early, skipped the check, or checked the wrong thing and accepted it: premature termination, no or incomplete verification, or incorrect verification.

## 6. Assert tool calls and final state, separately

Grade two different things, and do not grade the transcript's wording.

- **Tool calls.** The tool name, the arguments, and whether a write was allowed. These are deterministic. A test can say "lookup was called once with `sku=DL-14`" without caring how the model phrased the request.
- **Final outcome state.** The world after the run: the cart total, the file that was written, the row that was stored, the structured object that was returned. Compare that to the expected state.

A paragraph that reads well can still be a failed task, and a stiff paragraph can still be a correct one. [Anthropic's notes on their multi-agent research system](https://www.anthropic.com/engineering/built-multi-agent-research-system) are a useful picture of why an orchestrator-and-subagent design has to be debugged from the trace and the outcome, not from the final writeup alone.

## 7. Report reliability with pass^k, not only pass@k

[τ-bench](https://arxiv.org/abs/2406.12045) (arXiv:2406.12045) separates two readings of k trials:

- **pass@k** is the chance that at least one of k trials succeeds. That is a capability number. One lucky path counts.
- **pass^k** is the chance that all k trials succeed. That is a reliability number. An agent that acts on a user, a file, or a ticket has to be this, because a customer does not reroll the run.

When you quote a score, say which one it is. For a fix, show that pass^k moved, on the minimal repro, with the seed recorded.

## 8. If you use an LLM judge, make it narrow and check it

Prefer a code assertion whenever the failure is a fact a program can see (a tool argument, a number, a schema). Use a model only for the residue that needs judgment.

When you do, follow the [evals FAQ](https://hamel.dev/blog/posts/evals-faq/):

- One judge per failure mode, returning pass or fail. A 1–5 score hides the decision.
- Write the failure down before you write the prompt. If you cannot decide the label on an example, the definition is not ready.
- Validate the judge against human labels. Split those labels into train, dev, and test. The dev and test examples never go in the prompt.
- Report true positive rate and true negative rate. Raw agreement is misleading when failures are rare: a judge that always says pass looks accurate and catches nothing.

A judge that has not been checked against human labels is another agent in the system. Do not let it close a bug by itself.

## 9. Inject faults on purpose

A happy-path test will not show you what the agent does when a tool misbehaves. Add fixtures that produce:

- a timeout
- a crash or a connection reset
- a truncated tool output
- a corrupted tool output (valid shape, wrong unit, or an instruction hidden in the text)
- a missing function (the model names a tool that is not registered)
- a bad tool description (the docstring promises a side effect or a unit the code does not implement)

For each injection, assert the stopping behavior and the final state. In particular, assert that a write or send tool did not run. Recovering by guessing is a failure if the task required the tool result.

## 10. Checkpoint and replay

A bug you cannot replay is a story. For every run you might review, store:

- model id
- seed
- temperature
- the messages or inputs sent to the model
- the tool name, arguments, and output, including errors

Replay uses that record. Keep the seed and the temperature the same. Serve the recorded tool outputs instead of calling the network, so the repro does not depend on a live service and does not repeat a side effect. Change one thing at a time when you are testing a fix.

## 11. Cap the run, then ask a person

Every loop around a model or a tool needs a ceiling:

- turns
- retries
- tokens
- tool calls

When a ceiling is hit, stop and escalate to a person. Do not start a fresh loop, and do not catch the error and continue with an empty result. A silent empty result becomes the next agent's input, which is how a small fault turns into a confident wrong answer. The static scan flags unbounded loops, unlimited retries, and `except: pass` as smells. The cap still has to exist in the runtime, because a linter cannot see a limit that is only in a config file it was not shown.

## 12. Tool descriptions are code, and tool output is untrusted

Two different bugs live in the tool boundary.

**Descriptions as a defect.** The text you show the model is part of the program. If the description says a price is in whole currency units and the function returns cents, every later agent will be wrong in the same direction. Treat description changes like code changes: review them, and cover them with a test that checks the arguments the model is supposed to send and the value the tool actually returns.

**Descriptions and outputs as an attack surface.** Tool output is untrusted content. A page, a ticket, or a file can contain instructions aimed at the model. [Simon Willison's lethal trifecta](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/) is the dangerous combination of private data, untrusted content, and an exfiltration path. An agent that can read a private store, ingest something it did not write, and also call a tool that sends or writes, can be talked into moving the private data out.

Break the combination. Do not give one agent all three. Split permissions so the agent that reads untrusted text cannot call the send tool. Gate every write and send tool on an explicit approval flag that a person has to set. `agentdebug lint` reports `AGT007` when a tool-shaped function writes or sends without that kind of parameter. The finding is a hint to go read the function, not a vulnerability report.

## 13. Do not trust automated blame

The [Who&When benchmark](https://arxiv.org/abs/2505.00212) (arXiv:2505.00212) measures automatic failure attribution on multi-agent traces. The best method in that paper reaches about **53.5%** accuracy at naming the responsible agent and about **14.2%** at naming the decisive step. Some methods land below a random baseline on the step task.

Use an automatic "this agent, this step" label as a hint about where to look. Then read the trace and decide the first upstream failure yourself. Do not close the bug on the label.

## What to do with a finding

1. Confirm it in the trace, with `file:line` for the code that produced the step.
2. Shrink to a minimal repro and an N-1 replay.
3. Fix the earliest break.
4. Add a regression test that asserts the tool call and the final state.
5. Re-run the fault injections that should have caught it.

The step-by-step version of that hand-off is [WORKFLOW.md](WORKFLOW.md).

## References

- OpenTelemetry GenAI spans: <https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-spans/>
- Anthropic, built a multi-agent research system: <https://www.anthropic.com/engineering/built-multi-agent-research-system>
- MAST, Why Do Multi-Agent LLM Systems Fail?: <https://arxiv.org/abs/2503.13657>
- Hamel Husain, evals FAQ: <https://hamel.dev/blog/posts/evals-faq/>
- τ-bench: <https://arxiv.org/abs/2406.12045>
- Who&When, automated failure attribution: <https://arxiv.org/abs/2505.00212>
- Simon Willison, the lethal trifecta: <https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/>
