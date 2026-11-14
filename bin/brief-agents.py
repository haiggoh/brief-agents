#!/usr/bin/env python3
"""brief-agents CLI — generate / inspect the agent briefing index.

Developer note: this is the only place (besides the hook) that touches the filesystem for
real; the scan and assembly logic lives in the fail-safe, unit-tested brief_agents_core
module. The user-facing usage text is USAGE below (kept free of implementation prose)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import brief_agents_core as core  # noqa: E402

VERSION = "0.2.2"  # also in .claude-plugin/plugin.json and CHANGELOG.md

USAGE = """Usage:
  brief-agents.py generate      Rebuild the agent briefing index from live inputs and
                                re-stamp the staleness fingerprint. Prints the path.
                                (Bare invocation with no command also runs generate.)
  brief-agents.py show          Print the current index to stdout (generating it first if
                                missing or stale).
  brief-agents.py path          Print the index path.
  brief-agents.py stale         Exit 0 if the index is stale/missing, 1 if fresh (for scripts).
  brief-agents.py --help, -h    Print this text (exit 0).
  brief-agents.py --version, -V Print the version (exit 0).

Environment overrides (all optional; env beats the default):
  BRIEF_AGENTS_GLOBAL_CLAUDE_MD        global instruction file (default ~/.claude/CLAUDE.md)
  BRIEF_AGENTS_INSTALLED_PLUGINS_FILE  plugin registry (default ~/.claude/plugins/installed_plugins.json)
  BRIEF_AGENTS_INDEX_FILE              the generated index (default ~/.claude/agent-briefing-index.md)
  BRIEF_AGENTS_FINGERPRINT_FILE        staleness fingerprint (default ~/.claude/.brief-agents-fingerprint)
  BRIEF_AGENTS_MEMORY_INDEX_FILE       memory index to scan (default
                                       ~/.claude/projects/<cwd-slug>/memory/MEMORY.md)
"""


def main(argv):
    # Help/version win anywhere in argv: `brief-agents.py generate --help` must NOT run the
    # write verb the user was hovering over (review finding 5).
    if any(a in ("-h", "--help") for a in argv[1:]):
        sys.stdout.write(USAGE)
        return 0
    if any(a in ("-V", "--version") for a in argv[1:]):
        print(VERSION)
        return 0
    cmd = argv[1] if len(argv) > 1 else "generate"
    cwd = os.getcwd()

    if cmd == "generate":
        path = core.generate(cwd)
        print(path)
        return 0
    if cmd == "path":
        print(core.index_output_path())
        return 0
    if cmd == "stale":
        return 0 if core.is_stale(cwd) else 1
    if cmd == "show":
        if core.is_stale(cwd):
            core.generate(cwd)
        sys.stdout.write(core.read_text(core.index_output_path()))
        return 0

    sys.stderr.write("unknown command: %s\n" % cmd)
    sys.stderr.write(USAGE)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
