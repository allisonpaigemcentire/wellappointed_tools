# Review workflow

Use this when you are debugging an agent in a repository you can read. The method behind each step is in [PLAYBOOK.md](PLAYBOOK.md). Examples below are invented. Substitute your own paths, and keep private data out of the report you commit.

## 1. Scope

Write down, before you read code:

- The repository and the revision (a commit, a branch, or a trace id).
- The symptom a person actually saw, in one sentence.
- What you will not do: no live sends, no production credentials, no customer documents, no publishes.
- The commands you are allowed to run. Prefer an offline replay.

A scope that says "look at the agent" is too wide. "The cart total is 100x too small after a catalog lookup, revision abc123, offline replay only" is a review.

## 2. Collect traces and runs

Gather the runs that show the symptom and, if you have them, one run that does not.

- OpenTelemetry GenAI spans, or the JSONL schema in the [README](README.md#trace-schema).
- The code at the same revision as the run.
- The seed, temperature, and model id, if they were recorded.
- Any fault-injection or eval output you already have.

`agentdebug trace summarize trace.jsonl` prints each step's agent, tool calls, errors, and token counts, plus repeated steps and the first step that carries an error. That first error is not automatically the first upstream failure. A later timeout can be the first red span in a trace whose real break was a bad tool description with no exception.

## 3. Find the first upstream failure, with file:line

Read the trace from the start. For each step, ask whether every later step was still able to succeed. The first step where the answer is no is the cause. Later red spans are symptoms.

Write the evidence as `path:line`, plus the observation:

> `catalog.py:18` returns cents. `tools.py:40` describes the same field as whole currency units. The writer at step 4 multiplies a number that was already wrong. Step 4 is not the cause.

Label that one failure in your own words (open coding). If you are reviewing a batch, cluster the labels afterward (axial coding) and map them onto the MAST categories in the playbook. Do not start from the category.

An automatic blame label, including the first error line from the summarizer, is a place to look. The [Who&When](https://arxiv.org/abs/2505.00212) numbers in the playbook are why you still read the trace.

## 4. Minimal repro

Shrink the run until the failure still happens and every removed piece makes it stop happening. Then drop the last turn and replay the recorded prefix with the recorded seed and temperature (N-1). Keep the smallest prefix that is already wrong.

The repro names:

- the input
- the tools that must exist
- the recorded tool output, if the live tool is not required
- the expected final state
- the actual final state

Invented example. A shopping assistant calls `lookup_price`. The tool description says the result is a whole number of currency units. The function returns cents. The smallest repro is one lookup of a made-up sku `DL-14` whose recorded output is `1299`, and a cart total that should be `12.99` in that currency. Replaying without the writer turn still shows the wrong unit, so the writer is not part of the repro.

## 5. Proposed fix and a regression test

Fix the earliest break. In the example, change the description and the return value so they name the same unit, and scale the cart once.

The regression test should:

- run the real function or the real agent entrypoint against a fake model and the recorded tool output
- assert the tool call (name and arguments)
- assert the final cart state
- assert that a send or write tool was not called
- stay offline

Do not assert that the transcript contains a particular sentence. Wording tests pass while the total is still wrong, and fail when a correct answer is phrased differently.

Add the fault injection that would have caught this (a truncated price, a description that disagrees with the code) if it does not already exist.

## 6. Hand-off report

`agentdebug report init "desk lamp checkout"` writes a markdown file from the template below. Fill it in. Link the trace, the revision, the repro, and the test name. Say what you did not verify.

The report is the review. A chat message that says "fixed the price" is not.

## Report template

The installed copy lives at `src/agentdebug/templates/review_report.md`. `report init` fills in the title and the date. The body is:

```markdown
# Review: {{name}}

Date:
Reviewer:
Repo / revision:
Scope:

What was in bounds, which revision you read, and what you deliberately did not run or change (no publishes, no live credentials, no customer data).

## Bottom line

One short paragraph. Say whether the suspected failure holds, and name the first upstream failure in a single sentence.

## First upstream failure

Label only the earliest break in this trace. Later symptoms go under findings, not as extra root causes.

- Where: `path:line`
- What that code does:
- Why later stages could not recover:
- Evidence (trace step, command, or fixture):

## Suspected causes

| # | Cause | Verdict | Evidence |
|---|---|---|---|
| 1 | | Confirmed, refuted, or secondary | `file:line` |

## Findings, ranked

1. **Title.** What breaks, where (`file:line`), and the smallest observation that shows it.

## Transition matrix

Count first-upstream failures only. A row is the step that handed off; a column is the failure you observed at the next step.

| From step | To step | Failure | Count |
|---|---|---|---|
| | | | |

## Minimal repro

- Setup:
- Input:
- Expected final state:
- Actual final state:
- Tool-call assertion (name and arguments, not transcript wording):
- N-1 replay: drop the last turn, replay the recorded prefix with the recorded seed and temperature, and note whether the failure is already determined.

## Proposed fix

1. The change, and why it hits the first upstream failure rather than a downstream symptom.
2. Regression test: fixture, the tool call it asserts, and the final state it grades. Keep the test offline.

## Hand-off

- Confidence:
- Not verified:
- Caps or approval gates to add before the next live run:
- Suggested next step:
```
