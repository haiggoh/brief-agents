# brief-agents

A Claude Code plugin that closes a blind spot in delegation: **a subagent inherits none
of your durable rules.**

When your session delegates work through the **Agent** or **Workflow** tool, the spawned
subagent starts with a blank durable context. It does **not** see your global
`~/.claude/CLAUDE.md`, your project `CLAUDE.md`/`AGENTS.md`, your memory system, or the
SessionStart nudges your installed plugins inject into *your* context. So a subagent asked
to "fix this and make it live" can do exactly the wrong thing — e.g. hand-edit
`~/.claude/plugins/installed_plugins.json` instead of running `claude plugin update` —
purely because nobody told it the rule exists.

brief-agents fixes that by keeping a compact, always-current **agent briefing index** on
disk and nudging you to hand it to every code/architecture subagent you spawn.

## What it does

1. **Generates `~/.claude/agent-briefing-index.md`** — a compact, one-line-per-entry digest
   grouped by source:
   - **CLAUDE.md**: section headers + a one-line gist (global `~/.claude/CLAUDE.md` and any
     project `CLAUDE.md`/`AGENTS.md` under the cwd).
   - **Memory**: the entries already in `~/.claude/projects/<cwd-slug>/memory/MEMORY.md`,
     behavioural (`feedback`/`project`) first, each pointing at its file for full detail.
     Skipped silently if no memory index exists.
   - **Installed-plugin rules**: the **literal SessionStart nudge text** each plugin
     injects (falling back to its `plugin.json` description). This is the highest-value
     section — the actual rule wording, not a paraphrase.

   Built to be cheap to paste into a subagent prompt: hundreds of lines at most, a pointer
   to full detail rather than inlined text.

2. **Nudges the orchestrator** (SessionStart, model-facing — no user-visible banner): before
   invoking Agent/Workflow for architecture or code work, brief the subagent with the index
   (paste the relevant part, or tell it to read the file first).

3. **Regenerates only when sources change** — a cheap mtime fingerprint over the scanned
   files (sorted before hashing, so a harmless reorder doesn't trigger a rebuild) is
   compared against the last stamped fingerprint at SessionStart.

4. **Enforces at call time** (PreToolUse on `Agent`/`Task`/`Workflow`): a SessionStart
   nudge fires once and is easy to lose track of by the time you actually delegate. So at
   the moment of the call, if the delegation prompt looks architecture/code-shaped and
   references no briefing, the hook **blocks** an `Agent`/`Task` call (`permissionDecision:
   deny`) with a reason telling you to re-issue it after briefing the subagent with the
   index — or add `[no-brief]` to opt out. `Workflow` gets a softer, non-blocking
   `additionalContext` reminder (a workflow script always looks code-shaped, so hard-
   blocking every one would be too disruptive). Fail-safe: any error → allow, never crash.

A hook still cannot rewrite another tool call's arguments, so it can't auto-inject the
briefing text; what it can do is make the briefing exist, remind you at session start, and
stop an unbriefed code delegation at the moment it happens so you re-issue it correctly.

## Usage

Normally hands-off: the SessionStart hook keeps the index current. To drive it manually:

```
python3 bin/brief-agents.py generate   # rebuild the index + re-stamp the fingerprint
python3 bin/brief-agents.py show       # print it (rebuilding first if stale)
python3 bin/brief-agents.py path       # print the index path
python3 bin/brief-agents.py stale      # exit 0 if stale/missing, 1 if fresh
```

Then, when delegating code/architecture work, paste the relevant lines from
`~/.claude/agent-briefing-index.md` into the subagent's prompt, or tell it to read that
file first.

## Layout

```
.claude-plugin/plugin.json   plugin manifest (no `hooks` key — hooks auto-load)
hooks/hooks.json             SessionStart + PreToolUse wiring
hooks/brief-check.py         staleness check + regen + the model-facing nudge (SessionStart)
hooks/brief-pretool.py       call-time enforcement on Agent/Task/Workflow (PreToolUse)
bin/brief_agents_core.py     pure, fail-safe scan/parse/fingerprint/assembly logic
bin/brief-agents.py          CLI (generate / show / path / stale)
skills/brief-agents/SKILL.md the procedure: what the index is, when to brief, when to regen
tests/test_core.py           unit tests for scanning, extraction, ranking, fingerprint
tests/test_hook.sh           SessionStart hook emits a valid model-only nudge + regenerates
tests/test_pretool.sh        PreToolUse hook: deny/allow/soft-reminder/fail-safe cases
```

## Tests

```
python3 tests/test_core.py
bash    tests/test_hook.sh
bash    tests/test_pretool.sh
```

Both run directly against the source with no third-party dependencies.

## License

MIT © Heiko Brantsch
