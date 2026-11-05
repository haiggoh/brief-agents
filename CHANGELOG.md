# Changelog

## [0.2.0] — 2026-11-05

### Added — session-start PRIMER line for the brief-pretool guard

- `hooks/brief-pretool.py` (the Agent|Task|Workflow PreToolUse guard) carries a one-line
  `PRIMER` constant (149 chars) stating the rule imperatively. The existing SessionStart
  hook `hooks/brief-check.py` appends it as the nudge's final line — still ONE SessionStart
  injection — read via AST from `brief-pretool.py` (the guard module is never executed at
  session start), fail-open throughout.
- Both hooks now support `--help` (print the docstring, no hook JSON, exit 0).
- Tests extended in `tests/test_hook.sh` / `tests/test_pretool.sh` (PRIMER present, one line,
  carried as its own whole line in the SessionStart context, `--help` behaviour); suite
  ALL PASS.

## [0.1.8] — 2026-10-31

### Changed
- The plugin description (plugin.json, and the marketplace listing it feeds) is rewritten to describe
  the plugin's full current capabilities.

## [0.1.7] — 2026-10-31 — 📝: the credit-moment mark on the plugin's surfaces

- The repo's GitHub About emoji (📝) now leads what the user and model read at the plugin's credit
  moments (plan 2026-10-28, §Wave 3 Task 10): the SessionStart nudge's first token, the PreToolUse
  block reason (the plugin just prevented an unbriefed delegation — a credit moment), a ≤3-line
  Branding section in the SKILL.md, the plugin.json description, and the README h1.
- First CHANGELOG file for this repo (created with this entry).
- Tests: exact-prefix pins for the nudge and the block reason (test_hook.sh, test_pretool.sh).
