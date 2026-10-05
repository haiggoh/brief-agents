---
name: brief-agents
description: Use when you are about to delegate work to a subagent (the Agent or Workflow tool) for anything involving architecture decisions or writing code, and you want it to respect the durable rules THIS session knows but a fresh subagent does not. Invoke when briefing a subagent, when the agent-briefing index looks stale or wrong, when you want to regenerate it, or when you're deciding what context to hand a delegated agent. Also read this when you see the brief-agents SessionStart nudge and want to know how to act on it.
---

# brief-agents — hand delegated agents the rules they can't see

When your Claude Code session delegates work via the **Agent** or **Workflow** tool, the
spawned subagent starts with a **blank durable context**. It does **not** see:

- your global `~/.claude/CLAUDE.md` or any project `CLAUDE.md` / `AGENTS.md`,
- your memory system (`~/.claude/projects/<cwd-slug>/memory/`),
- the SessionStart **nudges** your installed plugins inject (the model-facing rules from
  no-hidden-changes, measure-twice, audit-loose-ends, waypoints, …).

Those are injected into **your** (the orchestrator's) context, not the subagent's. So a
subagent asked to "fix this and make it live" can do exactly the wrong thing — e.g.
hand-edit `~/.claude/plugins/installed_plugins.json` instead of using `claude plugin
update` — purely because **no one told it `no-hidden-changes` exists**. This plugin exists
to close that gap. It does **not** touch the subagent; it makes it easy for **you** to
brief it.

## The agent briefing index

`~/.claude/agent-briefing-index.md` is a compact, auto-maintained digest of your three
rule layers, grouped by source:

- **CLAUDE.md** — section headers + a one-line gist each (global and project-level).
- **Memory** — filtered to what a DELEGATED subagent actually needs, not a full MEMORY.md
  dump: `feedback` entries (explicit behavioral corrections — exactly what stops a
  subagent repeating a known mistake), plus `project` entries only when they describe a
  plugin/tool/script/MCP the agent might interact with. `user` and `reference` entries,
  and `project` entries that are really status logs (a migration report, a one-off
  creative project), are dropped — they're about *you*, not a guardrail the agent needs.
  Capped at a skimmable count with a "N more in MEMORY.md" pointer when trimmed — never a
  silent truncation. Skipped (with a note) if no memory index exists at the conventional
  path, or if nothing in it survives the filter.
- **Installed-plugin rules** — the **literal nudge text** each plugin injects at
  SessionStart (falling back to its `plugin.json` description). This is the highest-value
  section: the actual rule wording, not a paraphrase.

It is deliberately **one line per entry** with a path/name pointer, so the whole file is
cheap to paste into a subagent's prompt.

## When you delegate — the move

Before calling the Agent/Workflow tool for **architecture or code** work, do **one** of:

1. **Paste** the relevant lines from `~/.claude/agent-briefing-index.md` into the
   subagent's prompt (pick the sections that bear on its task — usually the plugin rules
   plus any on-point CLAUDE.md/memory lines), **or**
2. **Point** the subagent at the file: *"First read `~/.claude/agent-briefing-index.md`
   and follow any rule there that applies to this task."*

Prefer pasting the specific relevant rules for a focused task (cheaper, sharper); point at
the file for open-ended work where you can't predict what the subagent will touch.

## Briefing checklist — gaps a delegated agent will fill with plausible guesses

A generative model cannot leave a gap blank — every unstated detail becomes a plausible
GUESS asserted as fact. Before delegating, verify your brief covers these common silent
failure points:

- **Ordering of returned collections** — first vs last write wins? newest-first or
  oldest-first? state it explicitly.
- **Tie-breaking / precedence** — when two rules conflict, which wins? document it.
- **Inclusive vs exclusive boundaries** — is the interval `[start, end]` or `[start, end)`?
- **Empty / absent / malformed input** — what should the output be when the input is
  missing, empty, or doesn't match the expected shape?
- **Timezone- and locale-dependent values** — assert structurally (e.g. "ISO 8601"),
  not with an exact string that breaks in a different locale.

**Rule: ALWAYS mutation-test offloaded tests.** A passing test can hide a blind spot.
Example: deleting a `where !known.contains` guard did NOT fail
`testBaselineDoesNotOverwriteArchived` because `record(for:)` returns `.first` and the
duplicate record hid behind the still-correct first entry; the test only bit once it
asserted `records.count == 1` BEFORE unwrapping. If a test passes without the guard
it's meant to test, the test is not verifying what you think — mutation-test it by
temporarily breaking the code and confirming the test fails.

## Call-time enforcement (PreToolUse)

The SessionStart nudge fires once and is easy to lose track of by the time you actually
delegate. So a **PreToolUse hook** (`hooks/brief-pretool.py`, matcher `Agent|Task|Workflow`)
reinforces the rule at the moment of the call:

- **Agent / Task** with an architecture/code-shaped prompt that references no briefing →
  **blocked** (`permissionDecision: deny`) with a reason telling you to re-issue the call
  after briefing the subagent with the index. Add **`[no-brief]`** to the prompt to opt out
  when briefing is genuinely unneeded (e.g. a pure research/read-only delegation).
- **Workflow** → a non-blocking `additionalContext` reminder instead (a workflow script
  always looks code-shaped, so hard-blocking every one would be too disruptive).
- **`Agent(subagent_type="fork")`** → always allowed, no check performed. A fork inherits
  the caller's full conversation context rather than starting fresh, so there is no
  unbriefed subagent to catch — enforcing here would just force a meaningless `[no-brief]`
  tag onto every fork call.
- **Fail-safe:** any error, unparseable input, or missing field → allow, never crash a call.

A hook still cannot rewrite another tool call's arguments, so it can't auto-inject the
briefing text — but it *can* stop an unbriefed code delegation at the moment it happens so
you re-issue it correctly. Between the SessionStart nudge, the on-disk index, and this
gate, "I forgot to brief the subagent" stops being a silent failure.

## Regeneration & staleness

The SessionStart hook regenerates the index **only when its sources changed** — it
fingerprints the mtimes of the scanned CLAUDE.md/AGENTS.md files, the conventional
`MEMORY.md` (present or not), and `installed_plugins.json` (sorted before hashing, so a
harmless key reorder doesn't trigger a rebuild), and compares against the last stamped
fingerprint. You normally never regenerate by hand.

Regenerate manually when you've **just** changed a source mid-session and want the index
current before delegating:

```
python3 ~/ClaudeWorkspace/brief-agents/bin/brief-agents.py generate   # rebuild + re-stamp
python3 ~/ClaudeWorkspace/brief-agents/bin/brief-agents.py show       # print (rebuild if stale)
python3 ~/ClaudeWorkspace/brief-agents/bin/brief-agents.py path       # just the path
```

(When installed as a plugin the scripts live under the plugin cache; the `show`/`generate`
commands are the portable way to drive it. `generate` is safe to run repeatedly — atomic
write, no side effects beyond the index and its fingerprint file.)

## What it does NOT do

- It does not open every memory **file** — it uses the already-compact `MEMORY.md` index,
  so type tags are inferred from index cues and used only to rank, never asserted.
- It does not modify the subagent, CLAUDE.md, memory, or any plugin.
- It does not *auto-inject* briefing text into a subagent's prompt (a hook can't rewrite
  another tool's arguments) — it blocks/reminds so you re-issue the call briefed. The
  content judgment (which rules to paste) stays with you.

## The point

A delegated agent should never violate a rule simply because it was never told the rule
exists. Keep a current briefing on disk; hand the relevant part to every code/architecture
subagent you spawn.
