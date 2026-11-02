"""The package is named wellappointed-slopcheck, and install notes never point at the
unrelated `slopcheck` project on PyPI."""

import re
import tomllib
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parent
DIST = "wellappointed-slopcheck"
GIT_INSTALL = "git+https://github.com/allisonpaigemcentire/wellappointed_tools#subdirectory=slopcheck"

# `pip install slopcheck`, `pip install "slopcheck[suggest]"`, `pip install -U slopcheck==0.2`,
# `pipx install slopcheck`, or `uv tool install slopcheck`, with no git or path source.
BARE_PYPI = re.compile(
    r"""(?:pipx|pip3?|uv pip|uv tool|python3? -m pip) install(?:\s+-{1,2}[\w-]+)*\s+"""
    r"""["']?slopcheck(?:\[[a-z,]+\])?(?:[=<>~!]=?[\w.*]+)?["']?(?=\s|$|`)(?!\s*@)"""
)


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
    assert f'pip install "{DIST} @ {GIT_INSTALL}"' in text
    assert f'pip install "{DIST}[suggest] @ {GIT_INSTALL}"' in text
    assert "not on PyPI" in text
    assert "different project" in text


def test_action_sample_warns_about_the_pypi_name():
    text = (PACKAGE / "examples" / "github-action.yml").read_text(encoding="utf-8")
    assert "pip install ./slopcheck" in text
    assert "different project" in text
    assert f'pip install "{DIST} @ {GIT_INSTALL}"' in text


def test_bare_pypi_pattern_catches_the_old_wording():
    assert _bare_installs("pip install slopcheck")
    assert _bare_installs('pip install "slopcheck[suggest]"')
    assert not _bare_installs("pip install ./slopcheck")
    assert not _bare_installs(f'pip install "slopcheck @ {GIT_INSTALL}"')
    assert not _bare_installs(f'pip install "{DIST} @ {GIT_INSTALL}"')
    assert not _bare_installs("pip install wellappointed-slopcheck")
    assert _bare_installs("pipx install slopcheck")
    assert _bare_installs("uv tool install slopcheck")
    assert _bare_installs("pip install -U slopcheck")
    assert _bare_installs("python -m pip install slopcheck==0.2.0")
    assert not _bare_installs("pipx install ./slopcheck")


def test_distribution_is_renamed_but_module_and_command_are_not():
    meta = tomllib.loads((PACKAGE / "pyproject.toml").read_text(encoding="utf-8"))
    assert meta["project"]["name"] == DIST
    assert meta["project"]["scripts"] == {"slopcheck": "slopcheck.cli:main"}
    assert (PACKAGE / "src" / "slopcheck" / "__init__.py").is_file()
    assert "slopcheck" in meta["tool"]["setuptools"]["package-data"]


def test_git_installs_use_the_new_package_name():
    old = re.compile(r"""["']slopcheck(?:\[[a-z,]+\])?\s*@""")
    offenders = {}
    for path, text in _install_texts():
        hits = [line.strip() for line in text.splitlines() if old.search(line)]
        if hits:
            offenders[str(path.relative_to(REPO))] = hits
    assert offenders == {}


def test_no_doc_tells_you_to_install_agentdebug_from_pypi():
    # agentdebug is unclaimed on PyPI, so anyone could publish under that name later.
    bare = re.compile(BARE_PYPI.pattern.replace("slopcheck", "agentdebug"))
    paths = [REPO / "README.md", REPO / "agentdebug" / "README.md"]
    offenders = {
        str(path.relative_to(REPO)): hits
        for path in paths
        if path.is_file()
        and (hits := [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if bare.search(line)])
    }
    assert offenders == {}
    assert not bare.search('pip install "agentdebug @ git+https://example.invalid#subdirectory=agentdebug"')
    assert bare.search("pip install agentdebug")
