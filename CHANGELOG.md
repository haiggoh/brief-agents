# Changelog

## [0.2.7] — 2026-11-16

### Fixed — the ship gate never ran pytest: test_cmd quoted the invocation inside echo '...'

- The test_cmd ended in `echo 'PY=...; "$PY" -m pytest ...'`, so the gate PRINTED the suite
  command instead of running it (reproduced: --test-only on the v0.2.4 tag reported pass on a
  tree where pytest fails 4 tests). The pytest line is now unquoted and actually executes;
  verified by running the exact test_cmd string (rc=0, '13 passed'). run-to-completion 1.6.2
  now also refuses any test_cmd with a quoted interpreter call at the unpiped tail.

## [0.2.6] — 2026-11-16

### Docs — backfilled the 0.2.4/0.2.5 release notes

- The 0.2.4 and 0.2.5 CHANGELOG sections shipped as "(release notes go here)"
  placeholders (the bump tool seeds the new entry from a template). Backfilled with the
  real fixed-changes sections; the published GitHub release bodies were corrected to
  match. No code changes; portable/ rebuilt at 0.2.6 for the manifest/version
  consistency gate.

## [0.2.5] — 2026-11-16

### Fixed — shipped-state repair (v0.2.4 released with a stale portable manifest + CLI version)

- `--version` is now DERIVED from the plugin manifest next to the package root
  (`.claude-plugin/plugin.json`) — no hardcoded `VERSION` constant to drift on the next
  bump (test_cli already expected derivation; the constant made the released v0.2.4 tree
  fail its own gate: test_cli version test + test_portable freshness/same-version/
  entry-points, 4 failed).
- `portable/` rebuilt at the host version (the version-bump tool does not cover
  `portable/.claude-plugin/plugin.json`; a host bump now always needs a portable
  rebuild — recorded for the fleet).
- Full gate green on the shipped tree (pytest 13/13, shell suites 0, `--check` exit 0),
  verified directly before release.

## [0.2.4] — 2026-11-16

### Fixed — degraded scan no longer stamps the briefing fingerprint fresh

- `generate()` stamped `compute_fingerprint()` unconditionally, and the fingerprint is
  path + `st_mtime_ns` only. An input that EXISTS but cannot be READ (chmod/ACL — ctime
  moves, mtime does not; a directory EISDIRs) makes the fail-safe readers return `''`/`{}`,
  so an EMPTY index was latched FRESH forever and the PreToolUse guard pointed
  orchestrators at an index saying "_(none found)_".
- Now: if any fingerprint input exists but is unreadable, the index is still written but
  the stamp is the sentinel `UNREADABLE` (never a real hash) — `is_stale()` keeps its
  documented fail-safe True and the next SessionStart retries; once the input is
  readable again the real hash differs, content lands, fresh stamp.
- TDD: `test_generate_degraded_scan_no_fresh_stamp` RED on old code (3 failures) →
  GREEN on the fix; mutation (revert) → RED; restored → GREEN.

## [0.2.3] — 2026-11-15

### Added — Phase 4 Wave B: committed portable package (COORDINATION C1/C2)

- New `scripts/build-portable.py` (from the reviewed pilot pattern) generates the committed
  `portable/` package: same-name manifest, the skill, both hooks, and the CLI + core module
  at `scripts/` (moved from `bin/`; the hooks' `../bin` import path is rewritten to
  `../scripts` in the portable copies). Emits `portable/PORTABLE-BUILD.json`
  (haiggoh-portable-build/1) and a deterministic dist zip.
- Host doc fix folded into scope (user: issues found this session become scope): SKILL.md
  no longer hardcodes `~/ClaudeWorkspace/...` personal paths — it uses `${CLAUDE_PLUGIN_ROOT}`.
- `tests/test_portable.py` pins freshness, same-name manifest, no `bin/`, the host->portable
  set (byte-identical moves, hook path rewrite), closure, C2 schema, deterministic zip, and
  FUNCTIONAL proof on both entry points (CLI --version; the SessionStart hook emits the
  briefing nudge from the portable root). Gate now also runs tests/test_cli.py.

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

### Review round (DeepSeek V4.1 Flash, cross-family) fixes

- `--help` is a dedicated USAGE text (developer prose no longer leaks into it), documents
  the flags themselves and the bare-invocation default (which is `generate` — a WRITE), and
  names every env override INCLUDING the memory-index default
  (`~/.claude/projects/<cwd-slug>/memory/MEMORY.md`); the names are derived from
  `brief_agents_core`'s own lookups by the test, so doc and code cannot drift.
- Help/version are recognised ANYWHERE in argv: `brief-agents.py generate --help` used to
  run the write verb while the user hovered over help.
- Tests run with HOME and all five `BRIEF_AGENTS_*` vars redirected into the sandbox and
  assert --help/--version write NOTHING (a regression routing help through generate fails
  here instead of regenerating the tester's live index); `--version`/`-V` stdout is
  asserted exactly; both aliases are exercised.
- Hooks verified unaffected: both intercept `-h/--help` before shelling out.
- Waypoint recorded for a core design question the review raised (does generate() stamp
  the fingerprint fresh after an empty/failed input scan?).

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
