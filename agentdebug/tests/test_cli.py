"""Subcommands through python -m agentdebug."""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
FIXTURES = Path(__file__).parent / "fixtures"
ENV = os.environ.copy()
ENV["PYTHONPATH"] = str(SRC)


def _run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "agentdebug", *args],
        cwd=cwd or ROOT,
        env=ENV,
        text=True,
        capture_output=True,
        check=False,
    )


def test_help_lists_subcommands():
    result = _run("--help")
    assert result.returncode == 0
    assert "lint" in result.stdout
    assert "trace" in result.stdout
    assert "report" in result.stdout


def test_lint_text_and_json_exit_codes():
    bad = _run("lint", str(FIXTURES / "smells.py"))
    assert bad.returncode == 1
    for rule in (f"AGT00{n}" for n in range(1, 9)):
        assert rule in bad.stdout
    assert ": hint:" not in bad.stdout
    assert "hint:" in bad.stdout

    clean = _run("lint", str(FIXTURES / "clean.py"))
    assert clean.returncode == 0
    assert clean.stdout == "no findings\n"

    payload = _run("lint", str(FIXTURES / "smells.py"), "--format", "json")
    assert payload.returncode == 1
    rows = json.loads(payload.stdout)
    assert {row["rule_id"] for row in rows} == {f"AGT00{n}" for n in range(1, 9)}
    assert {"path", "line", "rule_id", "message", "hint"} <= set(rows[0])


def test_lint_missing_path():
    result = _run("lint", str(FIXTURES / "nope.py"))
    assert result.returncode == 2
    assert "not found" in result.stderr


def test_trace_summarize_text_and_json():
    text = _run("trace", "summarize", str(FIXTURES / "trace.jsonl"))
    assert text.returncode == 0
    assert "first_error_step: 2" in text.stdout
    assert "tools=search" in text.stdout

    data = _run("trace", "summarize", str(FIXTURES / "otel_spans.json"), "--format", "json")
    assert data.returncode == 0
    summary = json.loads(data.stdout)
    assert summary["first_error_step"] == 2
    assert summary["steps"][1]["error"] == "deadline exceeded"

    broken = _run("trace", "summarize", str(FIXTURES / "smells.py"))
    assert broken.returncode == 2


def test_report_init_from_cli(tmp_path: Path):
    created = _run("report", "init", "Desk lamp checkout", cwd=tmp_path)
    assert created.returncode == 0
    path = Path(created.stdout.strip())
    assert path.name == "Desk-lamp-checkout.md"
    body = path.read_text(encoding="utf-8")
    assert "# Review: Desk lamp checkout" in body
    assert "## First upstream failure" in body

    again = _run("report", "init", "Desk lamp checkout", cwd=tmp_path)
    assert again.returncode == 2
    assert "already exists" in again.stderr

    forced = _run("report", "init", "Desk lamp checkout", "--force", cwd=tmp_path)
    assert forced.returncode == 0
