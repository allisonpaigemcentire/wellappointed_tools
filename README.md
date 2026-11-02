# wellappointed_tools

Shared developer tools. Clone the repository and use the project you need. Each project is a top-level directory with its own install notes.

## agentdebug

[agentdebug](agentdebug/README.md) is a dependency-light Python toolkit for finding bugs in agentic and multi-agent systems. [PLAYBOOK.md](agentdebug/PLAYBOOK.md) describes the method: trace with the OpenTelemetry GenAI conventions, label only the first upstream failure in each trace, shrink to a minimal repro, and grade tool calls and final state rather than transcript wording. [WORKFLOW.md](agentdebug/WORKFLOW.md) is the review you can run on your own code. The `agentdebug` command scaffolds a review report, scans Python for a handful of agent-bug smells, and summarizes a JSONL or OpenTelemetry trace.

## slopcheck

[slopcheck](slopcheck/README.md) flags prose that reads like a model wrote it, and AI jargon a reader cannot check. It also flags a repeated phrase, a sentence copied from a brief, a flat rhythm, and a few edit leftovers such as a doubled word. It prints the line, the column, the matched words, and a plain-language fix. Run it on a file, a folder, or a pipe. Install notes, the jargon rules, and the pre-commit sample are in that directory.

## License

MIT. See [LICENSE](LICENSE). The copyright holder is the same as in [slopcheck/LICENSE](slopcheck/LICENSE).
