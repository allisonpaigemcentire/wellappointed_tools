"""Shipped files stay free of private notebook markers.

The author credit is allowed only in the credit files. The credit string is
read from pyproject.toml so this test does not keep a second copy of the name.
"""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", "uploads", "__pycache__", ".pytest_cache", ".venv", "venv", "dist", "build", "tests"}
SKIP_PARTS = SKIP_DIRS | {"slopcheck.egg-info"}
AUTHOR_FILES = {"README.md", "LICENSE", "CONTRIBUTING.md", "pyproject.toml"}
# A made-up marker. A previous test listed private project names here. That
# list is not part of this public package.
PLACEHOLDER = "zz-private-notebook-token"


def _files():
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_PARTS or part.endswith(".egg-info") for part in path.parts):
            continue
        if path.suffix.lower() in {".png", ".pyc"}:
            continue
        yield path


def test_placeholder_token_is_absent():
    offenders = []
    for path in _files():
        text = path.read_text(encoding="utf-8", errors="replace")
        if PLACEHOLDER in text:
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_author_name_only_in_credit_files():
    meta = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    names = [author.get("name", "") for author in meta["project"]["authors"]]
    parts = [part for name in names for part in name.split() if len(part) >= 3]
    assert parts, "expected an author credit in pyproject.toml"
    offenders = []
    for path in _files():
        if path.name in AUTHOR_FILES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for part in parts:
            if part in text:
                offenders.append(f"{path.relative_to(ROOT)}: {part}")
    assert offenders == []
