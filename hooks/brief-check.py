#!/usr/bin/env python3
"""brief-agents — SessionStart hook.

Two jobs, both fail-safe (any error -> exit 0 with a bare valid nudge, never crash the
session start):

  1. Self-contained STALENESS CHECK: cheaply fingerprint the scanned sources
     (global + project CLAUDE.md/AGENTS.md, the conventional MEMORY.md if present,
     installed_plugins.json) and regenerate ~/.claude/agent-briefing-index.md only when
     something changed since the last generation. Sorted-before-hash, mtime-based —
     mirrors no-hidden-changes' surfaces_fingerprint and get-haiggoh's throttle spirit.
     Does NOT depend on any other plugin being installed.

  2. MODEL-FACING NUDGE (hookSpecificOutput.additionalContext, no user-visible banner):
     tell the ORCHESTRATING Claude to brief subagents with the index before delegating
     architecture/code work. This is guidance for the orchestrator — the hook never
     touches the subagent; the subagent learns the rules only via what the orchestrator
     puts in its prompt or tells it to read. The nudge's final line is the PreToolUse
     guard's one-line PRIMER (read from brief-pretool.py via AST, never executed here).

Emits exactly one JSON object on stdout, matching the shape used by the sibling haiggoh
nudge plugins (audit-loose-ends / measure-twice / no-hidden-changes)."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bin"))

NUDGE = (
    "📝 brief-agents: when you invoke the Agent or Workflow tool for a task involving "
    "ARCHITECTURE decisions or WRITING CODE, first brief the subagent with the current "
    "agent-briefing index (~/.claude/agent-briefing-index.md) — either paste its relevant "
    "contents into the prompt or explicitly tell the subagent to read that file before "
    "starting. Do NOT assume a subagent inherits your CLAUDE.md, memory, or plugin rules: "
    "it starts with NONE of them, so a rule like 'never hand-edit installed_plugins.json — "
    "use claude plugin update' is invisible to it unless you pass it along. The index is "
    "kept current automatically; consult the brief-agents skill for when to regenerate or "
    "what to include."
)


def _refresh_index():
    """Regenerate the index iff stale. Wrapped so any failure is swallowed — the nudge
    must still emit even if generation blows up on some malformed input."""
    try:
        import brief_agents_core as core
        if core.is_stale(os.getcwd()):
            core.generate(os.getcwd())
    except Exception:
        pass


def _primer_line() -> str:
    """The PreToolUse guard's PRIMER as one line, read via AST from brief-pretool.py —
    a session-start hook never EXECUTES the guard module just to read a string.
    '' on any problem: the nudge must still emit."""
    import ast
    try:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "brief-pretool.py")
        with open(path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        for node in tree.body:
            # plain Assign and annotated AnnAssign both carry the PRIMER constant
            if isinstance(node, ast.Assign):
                targets, value = node.targets, node.value
            elif isinstance(node, ast.AnnAssign):
                if node.value is None:
                    continue  # bare annotation (PRIMER: str) carries no value
                targets, value = [node.target], node.value
            else:
                continue
            if any(isinstance(t, ast.Name) and t.id == "PRIMER" for t in targets):
                p = ast.literal_eval(value)
                if isinstance(p, str) and p.strip() and "\n" not in p:
                    return p
                return ""
        return ""
    except Exception:
        return ""


def main():
    if any(a in ("-h", "--help") for a in sys.argv[1:]):
        sys.stdout.write(__doc__ or "")
        return 0
    _refresh_index()
    ctx = NUDGE
    primer = _primer_line()
    if primer:
        ctx = NUDGE + "\n" + primer
    out = {"hookSpecificOutput": {"hookEventName": "SessionStart",
                                  "additionalContext": ctx}}
    sys.stdout.write(json.dumps(out) + "\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        # Absolute last-resort guard: still emit a valid nudge, never a traceback.
        sys.stdout.write(json.dumps({"hookSpecificOutput": {
            "hookEventName": "SessionStart", "additionalContext": NUDGE}}) + "\n")
        raise SystemExit(0)
