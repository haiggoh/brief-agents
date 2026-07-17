#!/usr/bin/env python3
"""brief-agents CLI — generate / inspect the agent briefing index.

Usage:
  brief-agents.py generate      Rebuild ~/.claude/agent-briefing-index.md from live inputs
                                and re-stamp the staleness fingerprint. Prints the path.
  brief-agents.py show          Print the current index to stdout (generating it first if
                                missing or stale).
  brief-agents.py path          Print the index path.
  brief-agents.py stale         Exit 0 if the index is stale/missing, 1 if fresh (for scripts).

This is the only place (besides the hook) that touches the filesystem for real; the scan
and assembly logic lives in the fail-safe, unit-tested brief_agents_core module."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import brief_agents_core as core  # noqa: E402


def main(argv):
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
    sys.stderr.write(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
