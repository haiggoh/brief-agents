"""The CLI dispatch surface: --help and --version must be first-class, not "unknown
command" (P0 2026-11-13, the plan's version/help item — probed: --help printed an error
line and exited 2, --version had no answer at all). An unknown command keeps its documented
exit 2. The version is derived from plugin.json so a bump cannot stale the test.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "bin" / "brief-agents.py"


def _run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args],
                          capture_output=True, text=True, timeout=30)


def test_help_is_first_class():
    r = _run("--help")
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
    assert "unknown command" not in r.stdout + r.stderr
    for sub in ("generate", "show", "path", "stale"):
        assert sub in r.stdout, f"--help must document {sub}"
    for var in ("BRIEF_AGENTS_INDEX_FILE", "BRIEF_AGENTS_FINGERPRINT_FILE",
                "BRIEF_AGENTS_GLOBAL_CLAUDE_MD", "BRIEF_AGENTS_INSTALLED_PLUGINS_FILE",
                "BRIEF_AGENTS_MEMORY_INDEX_FILE"):
        assert var in r.stdout, f"--help must name the env override {var}"


def test_version_matches_manifest():
    manifest = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    r = _run("--version")
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
    assert manifest["version"] in r.stdout, (r.stdout, manifest["version"])


def test_unknown_command_still_exits_2():
    r = _run("--bogus")
    assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)
    assert "unknown command" in r.stderr
