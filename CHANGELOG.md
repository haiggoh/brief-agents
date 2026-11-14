# Changelog

## [0.2.2] — 2026-11-14

### Fixed (desktop-migration FLEET Phase 1 P0: version/help)

- `--help` / `-h` are first-class now: the usage text (subcommands + all five
  `BRIEF_AGENTS_*` environment overrides, newly documented) exits 0. Before, both `--help`
  and `--version` fell into the unknown-command branch — an error line, exit 2, and no
  version answer at all (probed).
- `--version` / `-V` print the VERSION constant (0.2.2), which the new CLI test derives
  from plugin.json so a future bump cannot stale it. Unknown commands keep their documented
  exit 2.
- Freshness reviewed, no defect found: the staleness fingerprint is sorted-stream-safe and
  covered by test_fingerprint/test_is_stale; `show` regenerates when stale.

## [0.2.1] — 2026-11-12

### Fixed — the idempotency test could pass on coarse-mtime filesystems

- `tests/test_hook.sh` check 5 slept 0.02 s and compared `st_mtime_ns`; on a 1 s-granularity
  filesystem both reads could land in the same tick and pass even if the index was rewritten.
  It now plants an impossible mtime on the index (the fingerprint covers the SOURCES, so this
  does not make it stale) and asserts the planted value survives the second run. New check 5b
  is the planted positive: a changed source must rewrite the index, so check 5 can fail.
  Mutation-tested: an always-stale freshness check turns check 5 red. Test-only, no behaviour change.

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
