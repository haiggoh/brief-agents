#!/usr/bin/env bash
# Framework-free test for hooks/brief-check.py: it must emit ONE valid JSON object whose
# additionalContext carries the brief-agents nudge, with NO user-visible banner, and it
# must regenerate the index into the (env-redirected) output path. Requires python3.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
HOOK="$HERE/../hooks/brief-check.py"
fail=0
check() { if [ "$1" = 0 ]; then echo "  ok: $2"; else echo "  FAIL: $2"; fail=1; fi; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Redirect every filesystem target into the sandbox so the test never touches the real
# ~/.claude, and seed a minimal source set so generation has something to scan.
export BRIEF_AGENTS_INDEX_FILE="$TMP/agent-briefing-index.md"
export BRIEF_AGENTS_FINGERPRINT_FILE="$TMP/fp"
export BRIEF_AGENTS_GLOBAL_CLAUDE_MD="$TMP/CLAUDE.md"
export BRIEF_AGENTS_INSTALLED_PLUGINS_FILE="$TMP/installed_plugins.json"
export BRIEF_AGENTS_MEMORY_INDEX_FILE="$TMP/MEMORY.md"
printf '# G\n## A rule\nthe gist\n' > "$BRIEF_AGENTS_GLOBAL_CLAUDE_MD"
printf '{"plugins":{}}' > "$BRIEF_AGENTS_INSTALLED_PLUGINS_FILE"

OUT="$(python3 "$HOOK")"

# 1) valid JSON + correct shape; extract additionalContext
CTX="$(printf '%s' "$OUT" | python3 -c 'import json,sys
d=json.load(sys.stdin)
assert d["hookSpecificOutput"]["hookEventName"]=="SessionStart"
print(d["hookSpecificOutput"]["additionalContext"])')"
check $? "emits valid SessionStart additionalContext JSON"

# 2) model-only: no user-visible banner
case "$OUT" in *systemMessage*) check 1 "no systemMessage (model-only)";; *) check 0 "no systemMessage (model-only)";; esac

# 3) key content present
case "$CTX" in *"brief-agents:"*) check 0 "labelled 'brief-agents:'";; *) check 1 "labelled 'brief-agents:'";; esac
case "$CTX" in *"agent-briefing-index.md"*) check 0 "names the index file";; *) check 1 "names the index file";; esac
case "$CTX" in *"Agent or Workflow tool"*) check 0 "names the Agent/Workflow tool trigger";; *) check 1 "names the Agent/Workflow tool trigger";; esac
LC="$(printf '%s' "$CTX" | tr 'A-Z' 'a-z')"
case "$LC" in *"none of them"*) check 0 "warns subagent inherits none of the rules";; *) check 1 "warns subagent inherits none of the rules";; esac

# 4) it regenerated the index into the redirected path
[ -f "$BRIEF_AGENTS_INDEX_FILE" ]; check $? "regenerated the index at the output path"
grep -q "A rule" "$BRIEF_AGENTS_INDEX_FILE"; check $? "index contains the scanned CLAUDE.md section"

# 5) idempotent-when-fresh: a second run must NOT rewrite (fingerprint unchanged)
BEFORE="$(python3 -c 'import os,sys; print(os.stat(sys.argv[1]).st_mtime_ns)' "$BRIEF_AGENTS_INDEX_FILE")"
sleep 0.02
python3 "$HOOK" >/dev/null
AFTER="$(python3 -c 'import os,sys; print(os.stat(sys.argv[1]).st_mtime_ns)' "$BRIEF_AGENTS_INDEX_FILE")"
[ "$BEFORE" = "$AFTER" ]; check $? "does not rewrite the index when sources are unchanged"

[ "$fail" = 0 ] && echo "ALL PASS" || { echo "FAILURES"; exit 1; }
