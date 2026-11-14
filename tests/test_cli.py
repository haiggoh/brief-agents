"""The CLI dispatch surface: --help and --version must be first-class, not "unknown
command" (P0 2026-11-13, the plan's version/help item — probed: --help printed an error
line and exited 2, --version had no answer at all). An unknown command keeps its documented
exit 2. The version is derived from plugin.json so a bump cannot stale the test; the
documented env names are derived from brief_agents_core's own lookups so the help cannot
lie about them (review round, DeepSeek V4.1 Flash).

Every test runs against a redirected HOME + the five BRIEF_AGENTS_* vars pointed into
tmp_path, and the help/version tests assert NOTHING was written — a regression that routes
help through generate() must fail here, not regenerate the tester's live index.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "bin" / "brief-agents.py"

ENV_VARS = [
    "BRIEF_AGENTS_GLOBAL_CLAUDE_MD",
    "BRIEF_AGENTS_INSTALLED_PLUGINS_FILE",
    "BRIEF_AGENTS_INDEX_FILE",
    "BRIEF_AGENTS_FINGERPRINT_FILE",
    "BRIEF_AGENTS_MEMORY_INDEX_FILE",
]


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    for var in ENV_VARS:
        # inside home on purpose: a regression that writes on --help/--version must be
        # caught by _wrote_anything(home), not routed outside it by the overrides
        monkeypatch.setenv(var, str(home / f"{var}.txt"))
    yield home


def _run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args],
                          capture_output=True, text=True, timeout=30)


def _wrote_anything(home):
    return sorted(p.name for p in home.rglob("*") if p.is_file())


def test_help_is_first_class_and_writes_nothing(isolated_home):
    r = _run("--help")
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
    assert "unknown command" not in r.stdout + r.stderr
    assert "-h" in r.stdout and "--version" in r.stdout, "--help must document itself"
    assert "brief-agents.py generate" in r.stdout  # the Usage block, not incidental prose
    assert "no command is given" in r.stdout or "no command" in r.stdout, (
        "the bare-invocation default (a WRITE) must be documented")
    for var in ENV_VARS:
        assert var in r.stdout, f"--help must name the env override {var}"
    assert "BRIEF_AGENTS_MEMORY_INDEX_FILE" in r.stdout and (
        "MEMORY.md" in r.stdout), "the memory-index override owes its default"
    assert r.stdout.endswith("\n"), "the shell prompt must not glue to the last help line"
    assert "fail-safe" not in r.stdout, "developer prose does not belong in --help"
    assert _wrote_anything(isolated_home) == [], "help must write nothing"


def test_help_flag_anywhere_in_argv(isolated_home):
    """`brief-agents.py generate --help` used to DO REAL WORK (generate writes the index)
    because help was recognised only as argv[1]. Help anywhere in argv wins."""
    r = _run("generate", "--help")
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
    assert "unknown command" not in r.stdout + r.stderr
    assert _wrote_anything(isolated_home) == [], "--help after a verb must not generate"


def test_version_exact_and_writes_nothing(isolated_home):
    manifest = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    for flag in ("--version", "-V"):
        r = _run(flag)
        assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
        assert r.stdout == f"{manifest['version']}\n", (flag, r.stdout, r.stderr)
    assert _wrote_anything(isolated_home) == [], "--version must write nothing"


def test_documented_env_names_match_core():
    """The help's five env names are derived from core's own lookups: a name documented but
    not read by core (or read but not documented) fails — the doc cannot drift from the
    code it describes (review finding 10)."""
    usage = _run("--help").stdout
    documented = set(re.findall(r"BRIEF_AGENTS_[A-Z_]+", usage))
    core_src = (ROOT / "bin" / "brief_agents_core.py").read_text()
    actual = set(re.findall(r"BRIEF_AGENTS_[A-Z_]+", core_src))
    assert documented == actual, f"doc-vs-core divergence: doc={sorted(documented)} core={sorted(actual)}"


def test_unknown_command_still_exits_2():
    r = _run("--bogus")
    assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)
    assert "unknown command" in r.stderr
