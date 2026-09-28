#!/usr/bin/env bash
# Framework-free test for hooks/brief-pretool.py — call-time enforcement.
# Contract: Agent/Task with architecture/code-shaped + UNbriefed prompt -> deny; briefed,
# non-code, or [no-brief] -> allow (no output); Workflow -> soft additionalContext (never
# deny); malformed stdin -> allow, never crash. Requires python3.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
HOOK="$HERE/../hooks/brief-pretool.py"
fail=0
check() { if [ "$1" = 0 ]; then echo "  ok: $2"; else echo "  FAIL: $2"; fail=1; fi; }

run() { echo "$1" | python3 "$HOOK" 2>/dev/null; }

# 1. Agent + code + unbriefed -> deny
OUT="$(run '{"tool_name":"Agent","tool_input":{"prompt":"Implement a new feature in the auth module","description":"x"}}')"
echo "$OUT" | grep -q '"permissionDecision": "deny"'; check $? "Agent code+unbriefed -> deny"

# 2. Agent + code + briefed (references index) -> allow (empty output)
OUT="$(run '{"tool_name":"Agent","tool_input":{"prompt":"Refactor parser; read ~/.claude/agent-briefing-index.md first","description":""}}')"
[ -z "$OUT" ]; check $? "Agent code+briefed -> allow (no output)"

# 3. Agent + not code-shaped -> allow
OUT="$(run '{"tool_name":"Agent","tool_input":{"prompt":"Research and summarize tradeoffs","description":"no code"}}')"
[ -z "$OUT" ]; check $? "Agent non-code -> allow (no output)"

# 4. Workflow + code + unbriefed -> soft additionalContext, NOT deny
OUT="$(run '{"tool_name":"Workflow","tool_input":{"script":"await agent(\"refactor the module\")"}}')"
echo "$OUT" | grep -q '"additionalContext"'; check $? "Workflow code -> additionalContext present"
echo "$OUT" | grep -qv '"permissionDecision": "deny"'; check $? "Workflow code -> NOT deny"

# 5. [no-brief] opt-out -> allow
OUT="$(run '{"tool_name":"Agent","tool_input":{"prompt":"implement it [no-brief]","description":""}}')"
[ -z "$OUT" ]; check $? "[no-brief] opt-out -> allow"

# 6. Agent + subagent_type=fork + code-shaped + unbriefed -> allow (fork inherits context)
OUT="$(run '{"tool_name":"Agent","tool_input":{"subagent_type":"fork","prompt":"Implement a new feature in the auth module","description":"x"}}')"
[ -z "$OUT" ]; check $? "Agent fork code+unbriefed -> allow (no output)"

# 7. malformed stdin -> allow, no crash (exit 0, no output)
OUT="$(echo 'not json' | python3 "$HOOK" 2>/dev/null)"; rc=$?
[ "$rc" = 0 ] && [ -z "$OUT" ]; check $? "malformed stdin -> fail-safe allow (exit 0, no output)"

if [ "$fail" = 0 ]; then echo "ALL PASS"; else echo "SOME FAILED"; exit 1; fi
