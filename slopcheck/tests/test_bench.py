"""The bench harness runs. It is not itself the accuracy claim.

Numbers in the README are whatever `slopcheck bench` measures on the shipped
corpus. This file checks that the harness, the manifest, and that sentence agree.
"""

import json
from pathlib import Path

from slopcheck.bench import format_report, run_bench, shipped_bench_dir
from slopcheck.cli import main

ROOT = Path(__file__).resolve().parents[1]


def test_shipped_bench_matches_the_readme_sentence():
    report = run_bench(shipped_bench_dir() / "clean", shipped_bench_dir() / "labeled")
    sentence = report.summary_sentence()
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert sentence in readme
    assert report.clean_words > 500
    assert report.labeled_expected >= 8
    assert report.quiet_violations == 0
    assert "synthetic" in readme.lower() or "overstate" in readme.lower()


def test_bench_command_prints_the_rate(capsys):
    code = main(["bench"])
    assert code == 0
    out = capsys.readouterr().out
    assert "false flags per 1,000 words" in out
    assert "overstate" in out.lower()


def test_user_folder_is_measured_without_the_shipped_corpus(tmp_path, capsys):
    clean = tmp_path / "drafts"
    clean.mkdir()
    (clean / "note.md").write_text("The tests passed on Tuesday and the log was short.\n", encoding="utf-8")
    labeled = tmp_path / "labeled"
    labeled.mkdir()
    (labeled / "bad.md").write_text("The the door stuck in the frame.\n", encoding="utf-8")
    (labeled / "manifest.yaml").write_text(
        "cases:\n  - file: bad.md\n    expect: [doubled-word]\n",
        encoding="utf-8",
    )
    assert main(["bench", "--clean", str(clean), "--labeled", str(labeled), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["clean_files"] == 1
    assert payload["labeled_hit"] == 1
    assert payload["labeled_expected"] == 1
    assert payload["recall"] == 1


def test_format_report_includes_the_caveat():
    report = run_bench(shipped_bench_dir() / "clean", shipped_bench_dir() / "labeled")
    text = format_report(report)
    assert "overstate" in text.lower()
