"""Install notes never point at the unrelated `slopcheck` project on PyPI."""

import re
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parent
GIT_INSTALL = "git+https://github.com/allisonpaigemcentire/wellappointed_tools#subdirectory=slopcheck"

# `pip install slopcheck` or `pip install "slopcheck[suggest]"` with no git or path source.
BARE_PYPI = re.compile(r"""pip install\s+["']?slopcheck(?:\[[a-z,]+\])?["']?(?=\s|$|`)(?!\s*@)""")


def _install_texts():
    paths = [PACKAGE / "README.md", PACKAGE / "CONTRIBUTING.md", REPO / "README.md"]
    paths += sorted((PACKAGE / "examples").glob("*"))
    paths += sorted((PACKAGE / "src" / "slopcheck").glob("*.py"))
    for path in paths:
        if path.is_file():
            yield path, path.read_text(encoding="utf-8")


def _bare_installs(text):
    """Lines that tell the reader to run a bare PyPI install.

    A line that warns about the name clash ("different project") may quote the
    bare command, because it is telling the reader not to run it.
    """
    return [
        line.strip()
        for line in text.splitlines()
        if BARE_PYPI.search(line) and "different project" not in line
    ]


def test_no_doc_tells_you_to_install_slopcheck_from_pypi():
    offenders = {}
    for path, text in _install_texts():
        hits = _bare_installs(text)
        if hits:
            offenders[str(path.relative_to(REPO))] = hits
    assert offenders == {}


def test_readme_documents_the_git_install_and_the_name_clash():
    text = (PACKAGE / "README.md").read_text(encoding="utf-8")
    assert GIT_INSTALL in text
    assert "not on PyPI" in text


def test_action_sample_warns_about_the_pypi_name():
    text = (PACKAGE / "examples" / "github-action.yml").read_text(encoding="utf-8")
    assert "pip install ./slopcheck" in text
    assert "different project" in text
    assert GIT_INSTALL in text


def test_bare_pypi_pattern_catches_the_old_wording():
    assert _bare_installs("pip install slopcheck")
    assert _bare_installs('pip install "slopcheck[suggest]"')
    assert not _bare_installs("pip install ./slopcheck")
    assert not _bare_installs(f'pip install "slopcheck @ {GIT_INSTALL}"')
