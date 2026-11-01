# wellappointed_tools

Shared tools for teams that write and review prose.

## slopcheck

slopcheck flags prose that reads like a model wrote it, and AI jargon a reader cannot check. It prints the line, the column, the matched words, and a plain-language fix. Allison McEntire wrote the rules and released the tool under the MIT license in [slopcheck/LICENSE](slopcheck/LICENSE). The rule list, the jargon buckets, and the limits are in [slopcheck/README.md](slopcheck/README.md).

### Install

Python 3.11 or newer. The package is the `slopcheck/` directory of this repository.

```bash
pip install "slopcheck @ git+https://github.com/allisonpaigemcentire/wellappointed_tools.git#subdirectory=slopcheck"
```

The term suggester is optional:

```bash
pip install "slopcheck[suggest] @ git+https://github.com/allisonpaigemcentire/wellappointed_tools.git#subdirectory=slopcheck"
```

Pin a commit or a tag when you want a fixed revision:

```bash
pip install "slopcheck @ git+https://github.com/allisonpaigemcentire/wellappointed_tools.git@<commit>#subdirectory=slopcheck"
```

From a checkout of this repo:

```bash
pip install -e "slopcheck[dev]"
```

### CLI

```bash
slopcheck path/to/file.md
slopcheck docs/
slopcheck --json post.md
cat post.md | slopcheck
slopcheck --fail-on warning post.md
slopcheck --max-errors 0 --max-warnings 10 post.md
slopcheck --suggest-terms post.md
```

Exit status is `0` when the run is under the threshold, `1` when it is over, and `2` for bad arguments, a broken rules file, or `--suggest-terms` without the `suggest` extra. By default only errors fail the run. `--max-errors` defaults to 0. `--max-warnings` defaults to no limit. `--suggest-terms` lists rare words that are not already in the jargon dictionary. It needs `wordfreq` from the `suggest` extra.

### Pre-commit

pre-commit reads `.pre-commit-hooks.yaml` from the git root. This repo keeps that file next to the package, at [the hook manifest](slopcheck/.pre-commit-hooks.yaml), so a `repo:` hook entry will not find it. Install the console script with a local hook. Replace `<commit>` with the revision you want. The same snippet is in [slopcheck/examples/pre-commit-config.yaml](slopcheck/examples/pre-commit-config.yaml).

```yaml
repos:
  - repo: local
    hooks:
      - id: slopcheck
        name: slopcheck
        entry: slopcheck
        language: python
        types_or: [markdown, text, rst]
        additional_dependencies:
          - "slopcheck @ git+https://github.com/allisonpaigemcentire/wellappointed_tools.git@<commit>#subdirectory=slopcheck"
```

### GitHub Action

Install from the same git URL, then run the CLI on the files you want checked. A workflow you can adapt is in [slopcheck/examples/github-action.yml](slopcheck/examples/github-action.yml).

```yaml
name: prose

on:
  pull_request:

jobs:
  slopcheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install slopcheck
        run: pip install "slopcheck @ git+https://github.com/allisonpaigemcentire/wellappointed_tools.git@<commit>#subdirectory=slopcheck"
      - name: Check prose
        run: slopcheck --fail-on error docs/
```

Tests for this package run from `.github/workflows/slopcheck-ci.yml` when files under `slopcheck/` change. The job uses `working-directory: slopcheck`.
