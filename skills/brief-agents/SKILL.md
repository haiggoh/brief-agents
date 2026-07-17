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
- **Memory** — the one-line entries already in `MEMORY.md`, behavioural (`feedback` /
  `project`) first, each with the file to open for full detail. Skipped silently if no
  memory index exists at the conventional path.
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

This is a **nudge, not an enforcement** — a hook cannot rewrite another tool call's
arguments, so nothing forces compliance. The plugin's job is to make the briefing exist
and remind you to use it.

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
- It does not force the orchestrator to brief anyone — that judgment stays with you.

## The point

A delegated agent should never violate a rule simply because it was never told the rule
exists. Keep a current briefing on disk; hand the relevant part to every code/architecture
subagent you spawn.
