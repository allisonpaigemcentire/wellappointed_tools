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
