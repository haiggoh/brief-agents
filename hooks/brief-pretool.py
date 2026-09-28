#!/usr/bin/env python3
"""brief-agents — PreToolUse hook: CALL-TIME enforcement.

The SessionStart nudge alone proved too weak (it fires once, as one line among many, and
was missed in a real incident where an Agent got delegated architecture work unbriefed).
This hook reinforces the rule at the MOMENT an Agent/Task/Workflow call is made: if the
delegation looks like architecture/code work and carries no briefing reference, it
intervenes so the orchestrator re-issues the call WITH the agent-briefing index.

  * Agent/Task  -> permissionDecision "deny" (blocks; the reason tells the orchestrator to
                   re-issue after briefing, or add "[no-brief]" to opt out). This is the
                   incident case, where hard enforcement is wanted.
  * Workflow    -> non-blocking additionalContext reminder (a workflow script always looks
                   code-shaped, so hard-blocking every workflow would be too disruptive).

Agent(subagent_type="fork") is exempt: a fork inherits the caller's full conversation
context (including any briefing already established), so there is nothing to brief it
with — enforcing here would just force a meaningless "[no-brief]" tag on every fork call.

FAIL-SAFE above all: any error, unparseable stdin, or missing field -> emit nothing and
exit 0 (the tool call proceeds). A hook must never crash or wrongly block a call on a bug.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bin"))


def _index_path():
    try:
        import brief_agents_core as core
        return core.index_output_path()
    except Exception:
        return os.path.expanduser("~/.claude/agent-briefing-index.md")


# Word-bounded, conservative signals — one match flags "architecture/code-shaped". Kept
# specific (no bare "API"/"class"/"function") to avoid false-blocking ordinary prose.
CODE_SIGNALS = [
    r"\bimplement", r"\brefactor", r"\barchitect", r"\bdesign the\b",
    r"\bwrite (?:the )?code\b", r"\bcodebase\b", r"\bfix (?:the |this )?bug\b",
    r"\badd (?:a |the )?feature\b", r"\bmigration\b", r"\bendpoint\b",
    r"\bschema\b", r"\brewrite\b", r"\bpatch (?:the |a )?\w",
    r"\.(?:py|ts|tsx|js|jsx|go|java|rs|swift|php|rb|sh|yaml|yml)\b",
]
BRIEF_MARKERS = ["agent-briefing-index", "read the agent briefing", "[no-brief]", "[briefed]"]


def _is_code_shaped(text):
    return any(re.search(s, text, re.IGNORECASE) for s in CODE_SIGNALS)


def _is_briefed(text):
    return any(m in text for m in BRIEF_MARKERS)


def _is_fork(tool_name, tool_input):
    if tool_name != "Agent" or not isinstance(tool_input, dict):
        return False
    return str(tool_input.get("subagent_type", "")).strip().lower() == "fork"


def _delegation_text(tool_name, tool_input):
    """Pull the delegation intent out of the tool arguments. Note the real stdin schema:
    tool_name is top-level; the prompt/description/script live under payload['tool_input']."""
    if not isinstance(tool_input, dict):
        return ""
    if tool_name in ("Agent", "Task"):
        return " ".join(str(tool_input.get(k, "") or "") for k in ("prompt", "description"))
    if tool_name == "Workflow":
        return " ".join(str(tool_input.get(k, "") or "") for k in ("script", "scriptPath"))
    return ""


def _emit(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def main():
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return 0  # unparseable -> allow silently
    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {})
    if _is_fork(tool_name, tool_input):
        return 0  # a fork inherits full context -> no fresh subagent to brief
    text = _delegation_text(tool_name, tool_input)
    if not text.strip() or not _is_code_shaped(text) or _is_briefed(text):
        return 0  # nothing to enforce -> allow silently (no output = proceed)

    idx = _index_path()
    reason = ("brief-agents: this looks like architecture/code delegation, but the prompt "
              "doesn't reference the agent-briefing index. Re-issue the call after briefing the "
              "subagent with %s (paste the relevant rules or tell it to read that file) — or add "
              "'[no-brief]' to the prompt if briefing is genuinely unneeded." % idx)

    if tool_name in ("Agent", "Task"):
        _emit({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                      "permissionDecision": "deny",
                                      "permissionDecisionReason": reason}})
    else:  # Workflow -> soft, non-blocking reminder
        _emit({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                      "additionalContext": reason}})
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        raise SystemExit(0)  # last-resort guard: never block a tool call on error
