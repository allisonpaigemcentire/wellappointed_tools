# wellappointed_tools

Shared developer tools. Clone the repository and use the project you need. Each project is a top-level directory with its own install notes.

## agentdebug

[agentdebug](agentdebug/README.md) is a dependency-light Python toolkit for finding bugs in agentic and multi-agent systems. [PLAYBOOK.md](agentdebug/PLAYBOOK.md) describes the method: trace with the OpenTelemetry GenAI conventions, label only the first upstream failure in each trace, shrink to a minimal repro, and grade tool calls and final state rather than transcript wording. [WORKFLOW.md](agentdebug/WORKFLOW.md) is the review you can run on your own code. The `agentdebug` command scaffolds a review report, scans Python for a handful of agent-bug smells, and summarizes a JSONL or OpenTelemetry trace.

## slopcheck

[slopcheck](https://cursor.com/codebase/allisonpaigemcentire/slopcheck) is the owner's existing tool, kept in a private Origin repository (`https://origin.cursor.com/allisonpaigemcentire/slopcheck.git`, branch `main`). It is not in this tree. The environment that prepared the current branch could not authenticate to Origin, the codebase page requires a login, and there is no public GitHub copy. The tool was not rewritten. A later change can copy the source into `slopcheck/` once that repository is readable.

## License

There is no `LICENSE` file yet. The owner still needs to choose one. Nothing here should be treated as licensed for reuse until that file exists.
