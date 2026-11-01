"""Shipped files stay free of credentials. The author name stays in the credit files."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", "uploads", "__pycache__", ".pytest_cache", ".venv", "venv", "dist", "build", "tests"}
SKIP_PARTS = SKIP_DIRS | {"slopcheck.egg-info"}
AUTHOR_FILES = {"README.md", "LICENSE", "CONTRIBUTING.md", "pyproject.toml"}
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# Assignment-shaped secrets and known token prefixes. The prose word "token" is allowed.
SECRET = re.compile(
    r"(?i)(?:api[_-]?key|secret[_-]?key|access[_-]?token|refresh[_-]?token|private[_-]?key)\s*[:=]\s*\S+"
    r"|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"
    r"|(?:ghp_|gho_|github_pat_|xox[baprs]-|AKIA)[A-Za-z0-9_\-]{8,}"
)


def _files():
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_PARTS or part.endswith(".egg-info") for part in path.parts):
            continue
        if path.suffix.lower() in {".png", ".pyc"}:
            continue
        yield path


def test_no_emails_or_credentials():
    offenders = []
    for path in _files():
        text = path.read_text(encoding="utf-8", errors="replace")
        if EMAIL.search(text) or SECRET.search(text):
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_author_name_only_in_credit_files():
    offenders = []
    for path in _files():
        if path.name in AUTHOR_FILES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "Allison" in text or "McEntire" in text:
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []
