"""Smell rules, including one positive and one negative case for each."""

from pathlib import Path

import agentdebug.lint as lint
from agentdebug.lint import lint_path

FIXTURES = Path(__file__).parent / "fixtures"
RULES = {f"AGT00{n}" for n in range(1, 9)}


def _source(tmp_path: Path, source: str) -> list:
    path = tmp_path / "sample.py"
    path.write_text(source, encoding="utf-8")
    return lint_path(path)


def _ids(findings) -> set[str]:
    return {item.rule_id for item in findings}


def test_fixture_covers_every_rule():
    findings = lint_path(FIXTURES / "smells.py")
    assert _ids(findings) == RULES
    assert all(item.line >= 1 and item.hint for item in findings)


def test_clean_fixture_has_no_findings():
    assert lint_path(FIXTURES / "clean.py") == []


def test_directory_scan_skips_virtualenv(tmp_path: Path):
    live = FIXTURES / "smells.py"
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "app.py").write_text(live.read_text(encoding="utf-8"), encoding="utf-8")
    hidden = tmp_path / ".venv" / "lib"
    hidden.mkdir(parents=True)
    (hidden / "junk.py").write_text("api_key = 'local-only-static-string-0123456789'\n", encoding="utf-8")
    findings = lint_path(tmp_path)
    assert findings
    assert all(".venv" not in item.path for item in findings)


def test_swallowed_exception_positive_and_negative(tmp_path: Path):
    findings = _source(
        tmp_path,
        "try:\n"
        "    len(items)\n"
        "except:\n"
        "    return []\n",
    )
    assert _ids(findings) == {"AGT001"}
    quiet = _source(
        tmp_path,
        "try:\n"
        "    len(items)\n"
        "except ValueError:\n"
        "    log(items)\n"
        "    raise\n",
    )
    assert quiet == []


def test_except_pass_is_flagged(tmp_path: Path):
    findings = _source(
        tmp_path,
        "try:\n"
        "    parse(blob)\n"
        "except ValueError:\n"
        "    pass\n",
    )
    assert _ids(findings) == {"AGT001"}


def test_hardcoded_gate_positive_and_negative(tmp_path: Path):
    findings = _source(
        tmp_path,
        "def check_ready(item):\n"
        "    return True\n"
        "\n"
        "def finish():\n"
        "    return {'passed': True, 'findings': []}\n",
    )
    assert _ids(findings) == {"AGT002"}
    assert len(findings) == 2
    clean = _source(
        tmp_path,
        "def check_ready(item):\n"
        "    return bool(item)\n",
    )
    assert clean == []


def test_unbounded_loop_and_retry(tmp_path: Path):
    findings = _source(
        tmp_path,
        "def run(client, prompt):\n"
        "    while True:\n"
        "        client.chat.completions.create(model='demo', messages=[])\n"
        "\n"
        "def pull(client):\n"
        "    while True:\n"
        "        try:\n"
        "            return client.get('https://example.invalid')\n"
        "        except ConnectionError:\n"
        "            continue\n"
        "\n"
        "@retry\n"
        "def poll():\n"
        "    return None\n",
    )
    assert {"AGT003", "AGT004", "AGT006"} <= _ids(findings)
    capped = _source(
        tmp_path,
        "def run(client, prompt, max_turns=3):\n"
        "    turn = 0\n"
        "    while turn < max_turns:\n"
        "        turn += 1\n"
        "        client.chat.completions.create(model='demo', messages=[], timeout=5)\n"
        "\n"
        "@retry(stop=stop_after_attempt(2))\n"
        "def poll(client):\n"
        "    return client.get('https://example.invalid', timeout=5)\n",
    )
    assert capped == []


def test_unrelated_name_is_not_an_iteration_cap(tmp_path: Path):
    findings = _source(
        tmp_path,
        "def run(client, recap):\n"
        "    while True:\n"
        "        client.chat.completions.create(model='demo', messages=[], timeout=5)\n"
        "        recap.append('x')\n",
    )
    assert _ids(findings) == {"AGT003"}


def test_break_on_counter_caps_a_true_loop(tmp_path: Path):
    findings = _source(
        tmp_path,
        "def run(client):\n"
        "    attempt = 0\n"
        "    while True:\n"
        "        attempt += 1\n"
        "        client.chat.completions.create(model='demo', messages=[], timeout=5)\n"
        "        if attempt >= 3:\n"
        "            break\n",
    )
    assert findings == []


def test_silent_truncation(tmp_path: Path):
    findings = _source(
        tmp_path,
        "def pack(prompt, notes):\n"
        "    return prompt[:400], notes[:2]\n",
    )
    assert len(findings) == 1
    assert findings[0].rule_id == "AGT005"
    assert "prompt" in findings[0].message


def test_missing_timeout_ignores_dict_get(tmp_path: Path):
    findings = _source(
        tmp_path,
        "def read(mapping, client):\n"
        "    return mapping.get('k'), client.get('https://example.invalid', timeout=2)\n",
    )
    assert findings == []


def test_ungated_write_tool(tmp_path: Path):
    findings = _source(
        tmp_path,
        "@tool\n"
        "def send_note(channel, text):\n"
        "    client.post(channel, text)\n"
        "\n"
        "@tool\n"
        "def send_note_ok(channel, text, approved=False):\n"
        "    if not approved:\n"
        "        raise RuntimeError('approval required')\n"
        "    client.post(channel, text, timeout=5)\n",
    )
    assert _ids(findings) == {"AGT006", "AGT007"}
    assert any(item.rule_id == "AGT007" and item.line == 2 for item in findings)


def test_open_for_read_is_not_a_write_tool(tmp_path: Path):
    findings = _source(
        tmp_path,
        "@tool\n"
        "def load_note(path):\n"
        "    return open(path).read()\n",
    )
    assert findings == []


def test_secret_assignment_and_prefix(tmp_path: Path):
    findings = _source(
        tmp_path,
        "api_key = 'local-only-static-string-0123456789'\n"
        "token = 'placeholder'\n"
        "label = 'short'\n",
    )
    assert len(findings) == 1
    assert findings[0].rule_id == "AGT008"
    live = "sk" + "-" + ("b" * 20)
    prefixed = _source(tmp_path, f"label = '{live}'\n")
    assert _ids(prefixed) == {"AGT008"}


def test_environment_lookup_is_not_a_secret(tmp_path: Path):
    findings = _source(
        tmp_path,
        "import os\n"
        "def configured():\n"
        "    return os.environ['API_KEY']\n",
    )
    assert findings == []


def test_rules_are_sorted():
    findings = lint_path(FIXTURES / "smells.py")
    keys = [(item.path, item.line, item.rule_id) for item in findings]
    assert keys == sorted(keys)


def test_missing_path(tmp_path: Path):
    try:
        lint_path(tmp_path / "missing.py")
    except FileNotFoundError:
        return
    raise AssertionError("expected FileNotFoundError")


def test_prefix_pattern_matches_known_shapes():
    pattern = lint._secret_prefix()
    samples = [
        "sk" + "-" + ("c" * 16),
        "gh" + "p_" + ("d" * 8),
        "AK" + "IA" + "0" * 16,
    ]
    for sample in samples:
        assert pattern.search(sample), sample
    assert pattern.search("local-only-static-string-0123456789") is None


# Regression cases from the 2026-11-02 review.


def test_max_tokens_is_not_an_iteration_cap(tmp_path: Path):
    findings = _source(
        tmp_path,
        "MAX_TOKENS = 512\n"
        "def run(client, prompt):\n"
        "    max_tokens = MAX_TOKENS\n"
        "    while True:\n"
        "        resp = client.chat.completions.create(model='m', messages=[], max_tokens=max_tokens, timeout=5)\n"
        "        if resp.done:\n"
        "            return resp\n",
    )
    assert _ids(findings) == {"AGT003"}
    for knob in ("max_output_tokens", "max_completion_tokens", "max_new_tokens"):
        source = (
            "def run(client):\n"
            "    while True:\n"
            f"        client.responses.create(model='m', {knob}=64, timeout=5)\n"
        )
        assert _ids(_source(tmp_path, source)) == {"AGT003"}, knob


def test_cap_name_compared_and_exited_counts(tmp_path: Path):
    findings = _source(
        tmp_path,
        "MAX_TURNS = 8\n"
        "def run(client):\n"
        "    turn = 0\n"
        "    while True:\n"
        "        turn += 1\n"
        "        client.chat.completions.create(model='m', messages=[], max_tokens=64, timeout=5)\n"
        "        if turn >= MAX_TURNS:\n"
        "            raise RuntimeError('turn budget spent')\n",
    )
    assert findings == []


def test_cap_name_outside_a_compare_does_not_count(tmp_path: Path):
    findings = _source(
        tmp_path,
        "def run(client, max_turns=3):\n"
        "    while True:\n"
        "        client.chat.completions.create(model='m', messages=[], timeout=5)\n"
        "        log(max_turns)\n",
    )
    assert _ids(findings) == {"AGT003"}


def test_current_openai_key_shapes_are_secrets(tmp_path: Path):
    pattern = lint._secret_prefix()
    for prefix in ("proj", "svcacct", "admin"):
        sample = "sk" + "-" + prefix + "-" + ("Ab3_" * 6)
        assert pattern.search(sample), prefix
    live = "sk" + "-" + "proj" + "-" + ("abcdefgh1234" * 2)
    findings = _source(tmp_path, f"import os\nAPI_KEY = os.environ.get('API_KEY', '{live}')\n")
    assert _ids(findings) == {"AGT008"}


def test_requests_session_constructor_needs_no_timeout(tmp_path: Path):
    findings = _source(
        tmp_path,
        "import requests\n"
        "session = requests.Session()\n"
        "def fetch(url):\n"
        "    return session.get(url, timeout=5)\n",
    )
    assert findings == []
    still_flagged = _source(tmp_path, "import httpx\nclient = httpx.Client()\n")
    assert _ids(still_flagged) == {"AGT006"}


def test_self_attribute_client_needs_a_timeout(tmp_path: Path):
    findings = _source(
        tmp_path,
        "import requests\n"
        "class Agent:\n"
        "    def __init__(self):\n"
        "        self.http = requests.Session()\n"
        "    def lookup(self, sku):\n"
        "        return self.http.get(f'https://example.invalid/{sku}')\n",
    )
    assert [(item.rule_id, item.line) for item in findings] == [("AGT006", 6)]
    assert "self.http.get" in findings[0].message


def test_client_built_with_timeout_covers_its_calls(tmp_path: Path):
    findings = _source(
        tmp_path,
        "from openai import OpenAI\n"
        "client = OpenAI(timeout=30)\n"
        "class Agent:\n"
        "    def __init__(self):\n"
        "        self.llm = OpenAI(timeout=30)\n"
        "    def ask(self):\n"
        "        return self.llm.chat.completions.create(model='m', messages=[])\n"
        "def ask():\n"
        "    return client.chat.completions.create(model='m', messages=[])\n",
    )
    assert findings == []


def test_broad_except_returning_empty_is_flagged(tmp_path: Path):
    for body in ("return []", "return None", "return", "return {}", "return ''", "continue"):
        source = (
            "def fetch(items):\n"
            "    for item in items:\n"
            "        try:\n"
            "            return load(item)\n"
            "        except Exception:\n"
            f"            {body}\n"
        )
        findings = _source(tmp_path, source)
        assert _ids(findings) == {"AGT001"}, body
        assert "empty result" in findings[0].message
    tuple_form = _source(
        tmp_path,
        "def fetch():\n"
        "    try:\n"
        "        return load()\n"
        "    except (ValueError, BaseException):\n"
        "        return []\n",
    )
    assert _ids(tuple_form) == {"AGT001"}


def test_logged_or_narrow_empty_return_is_quiet(tmp_path: Path):
    findings = _source(
        tmp_path,
        "def fetch():\n"
        "    try:\n"
        "        return load()\n"
        "    except Exception:\n"
        "        log.exception('load failed')\n"
        "        return []\n"
        "\n"
        "def lookup(table, key):\n"
        "    try:\n"
        "        return table[key]\n"
        "    except KeyError:\n"
        "        return None\n"
        "\n"
        "def parse(blob):\n"
        "    try:\n"
        "        return decode(blob)\n"
        "    except Exception:\n"
        "        return fallback(blob)\n",
    )
    assert findings == []


def test_log_preview_slice_is_not_truncation(tmp_path: Path):
    findings = _source(
        tmp_path,
        "import logging, sys\n"
        "logger = logging.getLogger(__name__)\n"
        "def preview(text, prompt):\n"
        "    print(text[:80])\n"
        "    logger.info('prompt %s', prompt[:120])\n"
        "    sys.stderr.write(f'{text[:40]}\\n')\n"
        "    self_log = None\n",
    )
    assert findings == []
    still_flagged = _source(tmp_path, "def call(llm, prompt):\n    return llm(prompt[:400])\n")
    assert _ids(still_flagged) == {"AGT005"}


def test_tool_substring_and_stdout_are_not_write_tools(tmp_path: Path):
    findings = _source(
        tmp_path,
        "import sys\n"
        "def render_toolbar(items):\n"
        "    sys.stdout.write(','.join(items))\n"
        "\n"
        "@toolbar.register\n"
        "def draw(items):\n"
        "    items.remove(None)\n",
    )
    assert findings == []
    still_flagged = _source(
        tmp_path,
        "def delete_tool(path):\n"
        "    path.unlink()\n"
        "\n"
        "@mcp.tool()\n"
        "def wipe(path):\n"
        "    path.unlink()\n",
    )
    assert [item.rule_id for item in still_flagged] == ["AGT007", "AGT007"]


def test_event_loop_with_except_continue_is_not_a_retry(tmp_path: Path):
    findings = _source(
        tmp_path,
        "def poll_events(queue, max_events=100):\n"
        "    while True:\n"
        "        try:\n"
        "            item = queue.get()\n"
        "        except KeyError:\n"
        "            continue\n"
        "        handle(item)\n",
    )
    assert findings == []
    retry = _source(
        tmp_path,
        "def pull(session):\n"
        "    while True:\n"
        "        try:\n"
        "            return session.get('https://example.invalid', timeout=5)\n"
        "        except ConnectionError:\n"
        "            continue\n",
    )
    assert _ids(retry) == {"AGT004"}


def test_review_sample_agent_findings():
    findings = lint_path(FIXTURES / "review_agent.py")
    got = sorted((item.line, item.rule_id) for item in findings)
    assert got == [(12, "AGT003"), (21, "AGT001"), (30, "AGT006"), (56, "AGT008")]
