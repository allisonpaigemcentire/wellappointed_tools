"""CLI output, exit codes, stdin, and user overlays."""

import json
import sys
from io import StringIO
from pathlib import Path

import pytest

from slopcheck.cli import main
from slopcheck.load import (
    ConfigError,
    load_jargon,
    load_rules,
    merge_jargon,
    merge_rules,
)


def write(tmp_path: Path, text: str, name: str = "note.md") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_error_exits_nonzero_and_json_has_fields(tmp_path, capsys):
    path = write(tmp_path, "Please delve now.\n")
    code = main(["--json", str(path)])
    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["summary"]["errors"] == 1
    finding = payload["findings"][0]
    assert finding["line"] == 1
    assert finding["column"] == 8
    assert finding["match"] == "delve"
    assert finding["category"] == "ai-tell"
    assert finding["severity"] == "error"
    assert finding["suggestion"]


def test_max_errors_allows_a_hit(tmp_path, capsys):
    path = write(tmp_path, "Please delve now.\n")
    assert main(["--max-errors", "5", str(path)]) == 0


def test_em_dash_warning_does_not_fail_until_asked(tmp_path, capsys):
    path = write(tmp_path, "One — two — three — done.\n")
    assert main([str(path)]) == 0
    out = capsys.readouterr().out
    assert "warning: em-dash:" in out
    assert main(["--fail-on", "warning", str(path)]) == 1


def test_missing_file_exits_2(tmp_path, capsys):
    assert main([str(tmp_path / "missing.md")]) == 2
    assert "file not found" in capsys.readouterr().err


def test_stdin_and_text_report(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", StringIO("The result? Review time doubled.\n"))
    code = main(["-"])
    assert code == 1
    out = capsys.readouterr().out
    assert "<stdin>:1:" in out
    assert "reveal-fragment" in out
    assert "1 error" in out


def test_no_args_on_a_tty_exits_2(monkeypatch, capsys):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    assert main([]) == 2


def test_directory_scan(tmp_path, capsys):
    write(tmp_path, "Please delve now.\n", "a.md")
    write(tmp_path, "The tests passed.\n", "b.txt")
    (tmp_path / "skip.py").write_text("delve = 1\n", encoding="utf-8")
    assert main([str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "a.md" in out
    assert "delve" in out
    assert "skip.py" not in out


def test_no_jargon_skips_replace_terms(tmp_path):
    path = write(tmp_path, "Our agentic tools ran overnight.\n")
    assert main(["--no-jargon", str(path)]) == 0


def test_user_rules_disable_and_add(tmp_path, capsys):
    rules = tmp_path / "rules.yaml"
    rules.write_text(
        "disable:\n  - delve\npatterns:\n"
        "  - id: circle-back\n    category: filler-hedge\n    severity: error\n"
        "    pattern: '\\bcircle back\\b'\n    suggestion: Say when you will reply.\n",
        encoding="utf-8",
    )
    path = write(tmp_path, "Please delve now and circle back tomorrow.\n")
    assert main(["--rules", str(rules), str(path)]) == 1
    out = capsys.readouterr().out
    assert "delve" not in out
    assert "circle-back" in out or "circle back" in out


def test_project_config(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".slopcheck.yaml").write_text("max_errors: 5\nno_emdash: true\n", encoding="utf-8")
    write(tmp_path, "Please delve now.\n")
    assert main([str(tmp_path / "note.md")]) == 0


def test_bad_jargon_file(tmp_path, capsys):
    bad = tmp_path / "bad.yaml"
    bad.write_text("entries:\n- {term: x, bucket: nope, plain: y, false_friend: false, aliases: [x]}\n", encoding="utf-8")
    path = write(tmp_path, "Hello.\n")
    assert main(["--jargon", str(bad), str(path)]) == 2
    assert "bucket must be one of" in capsys.readouterr().err


def test_merge_helpers_override_by_id():
    base = load_rules()
    merged = merge_rules(base, "disable:\n  - ultimately\nem_dash:\n  max_per_window: 1\n", "user.yaml")
    assert all(pattern.id != "ultimately" for pattern in merged.patterns)
    assert merged.em_dash.max_per_window == 1
    jargon = load_jargon()
    overlay = merge_jargon(jargon, "entries:\n- {term: temperature, bucket: keep, plain: heat, false_friend: false}\n", "j.yaml")
    temp = next(entry for entry in overlay if entry["term"] == "temperature")
    assert temp["bucket"] == "keep"
    with pytest.raises(ConfigError):
        merge_jargon(jargon, "entries:\n- {term: temperature, bucket: keep, plain: heat, false_friend: true}\n", "j.yaml")


def test_docs_have_no_findings():
    root = Path(__file__).resolve().parents[1]
    assert main([
        "--fail-on", "warning",
        str(root / "README.md"),
        str(root / "CONTRIBUTING.md"),
    ]) == 0


def test_sample_before_fails_and_after_is_clean():
    root = Path(__file__).resolve().parents[1]
    assert main([str(root / "examples" / "sample-before.md")]) == 1
    assert main([str(root / "examples" / "sample-after.md")]) == 0


def test_clean_file_reports_no_findings(tmp_path, capsys):
    path = write(tmp_path, "The tests passed on Tuesday.\n")
    assert main([str(path)]) == 0
    assert "No findings" in capsys.readouterr().out
