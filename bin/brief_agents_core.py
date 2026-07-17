"""Pure, unit-testable core for brief-agents.

Scans the three durable-rule layers a Claude Code orchestrator session sees — but a
freshly-spawned subagent does NOT — and distils them into one compact "agent briefing
index" (~/.claude/agent-briefing-index.md). The orchestrator can then paste that file
(or point the subagent at it) so delegated work starts knowing the rules instead of
re-deriving them (or violating one blindly, e.g. hand-editing installed_plugins.json
because it never heard of no-hidden-changes).

Design rules mirrored from get-haiggoh's core:
  * No subprocess/network here. bin/brief-agents.py and hooks/brief-check.py are the only
    places that shell out; this module is trivially mockable in tests.
  * Every loader/scanner is FAIL-SAFE — a missing/corrupt input returns an empty
    structure, never raises. A SessionStart hook must not crash on a malformed file.
  * Compact by construction: one line per entry, a pointer (path/name) to full detail
    on demand — never the full text inlined. The whole file must be cheap to paste into
    a subagent's prompt.
"""
import glob
import hashlib
import json
import os
import re
import tempfile


# ---------------------------------------------------------------------------
# Paths (all overridable via env for testing)
# ---------------------------------------------------------------------------

def global_claude_md_path():
    return os.environ.get("BRIEF_AGENTS_GLOBAL_CLAUDE_MD") or os.path.expanduser(
        "~/.claude/CLAUDE.md")


def installed_plugins_path():
    return os.environ.get("BRIEF_AGENTS_INSTALLED_PLUGINS_FILE") or os.path.expanduser(
        "~/.claude/plugins/installed_plugins.json")


def index_output_path():
    return os.environ.get("BRIEF_AGENTS_INDEX_FILE") or os.path.expanduser(
        "~/.claude/agent-briefing-index.md")


def fingerprint_path():
    return os.environ.get("BRIEF_AGENTS_FINGERPRINT_FILE") or os.path.expanduser(
        "~/.claude/.brief-agents-fingerprint")


def cwd_slug(cwd):
    """Convention: cwd with '/' and '.' replaced by '-'. Matches how Claude Code names
    the per-project memory directory under ~/.claude/projects/<slug>/."""
    return cwd.replace("/", "-").replace(".", "-")


def memory_index_path(cwd, home=None):
    """Conventional MEMORY.md path for the given cwd, or None env override.

    Returns the path string unconditionally (existence is checked by the caller — the
    scanner is defensive about a missing file)."""
    override = os.environ.get("BRIEF_AGENTS_MEMORY_INDEX_FILE")
    if override:
        return override
    home = home or os.path.expanduser("~")
    return os.path.join(home, ".claude", "projects", cwd_slug(cwd), "memory", "MEMORY.md")


# ---------------------------------------------------------------------------
# Fail-safe primitives
# ---------------------------------------------------------------------------

def read_text(path):
    """Fail-safe text read: missing/unreadable -> ''."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return ""


def load_json(path):
    """Fail-safe JSON read: missing/malformed -> {}."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _collapse(s, limit=200):
    """Collapse whitespace to single spaces and truncate to `limit` chars."""
    s = re.sub(r"\s+", " ", s or "").strip()
    if len(s) > limit:
        s = s[: limit - 1].rstrip() + "…"
    return s


# ---------------------------------------------------------------------------
# CLAUDE.md / AGENTS.md scanning
# ---------------------------------------------------------------------------

def _gist_after_header(lines, header_idx):
    """First non-blank, non-header prose line after a header index, collapsed short."""
    for j in range(header_idx + 1, len(lines)):
        ln = lines[j].strip()
        if not ln:
            continue
        if ln.startswith("#"):
            break  # next header before any prose -> no gist
        # strip common list/quote markers for a cleaner one-liner
        ln = re.sub(r"^[>*\-]\s*", "", ln)
        return _collapse(ln, 120)
    return ""


def scan_claude_md(text):
    """Extract (header, one-line-gist) pairs from a CLAUDE.md / AGENTS.md body.

    Compactness over completeness: we keep the ## / ### section headers (the top H1 is
    usually just a title) and one gist line each. Returns [] for empty/headerless text."""
    if not text:
        return []
    lines = text.splitlines()
    out = []
    for i, raw in enumerate(lines):
        m = re.match(r"^(#{2,4})\s+(.*\S)\s*$", raw)
        if not m:
            continue
        header = _collapse(m.group(2), 90)
        gist = _gist_after_header(lines, i)
        out.append((header, gist))
    return out


def find_project_claude_mds(cwd):
    """Project-level CLAUDE.md / AGENTS.md under the cwd tree (not the global ~/.claude one).

    Shallow, bounded walk: skips VCS/dependency/cache dirs and caps depth so a scan from a
    huge tree stays cheap. Returns absolute paths, deterministically sorted."""
    skip = {".git", "node_modules", ".venv", "venv", "__pycache__", ".mypy_cache",
            ".pytest_cache", "dist", "build", ".next", "target", ".cache"}
    names = {"CLAUDE.md", "AGENTS.md"}
    found = []
    cwd = os.path.abspath(cwd)
    base_depth = cwd.rstrip(os.sep).count(os.sep)
    for root, dirs, files in os.walk(cwd):
        # prune noisy dirs and hidden dirs (but allow the top-level itself)
        dirs[:] = [d for d in dirs if d not in skip and not d.startswith(".")]
        if root.count(os.sep) - base_depth >= 4:
            dirs[:] = []  # depth cap
        for fn in files:
            if fn in names:
                found.append(os.path.join(root, fn))
    return sorted(found)


# ---------------------------------------------------------------------------
# Memory index scanning (defensive: file may not exist)
# ---------------------------------------------------------------------------

_MEM_TYPE_RE = re.compile(r"\btype[:=]\s*(user|feedback|project|reference)\b", re.I)

# How many filtered (feedback + tool-relevant-project) memory entries to inline before
# switching to a "N more — read the file" pointer. Picked to keep the section a skimmable
# guardrail list rather than a second copy of MEMORY.md; NOT a silent cap — cap_with_pointer
# always emits a pointer line when it trims, per the house no-silent-caps rule.
MEMORY_AGENT_LIMIT = 18


def parse_memory_index(text):
    """Parse the one-line entries out of a MEMORY.md index body.

    MEMORY.md is already a maintained, compact index — each bullet is
    `- [Title](file.md) — gist`. We keep title, file, gist, and (best-effort) a type
    inferred from keywords in the gist since the type: tag lives in each memory FILE's
    frontmatter, not the index. Returns [] for empty/non-index text (fail-safe)."""
    if not text:
        return []
    out = []
    for raw in text.splitlines():
        ln = raw.strip()
        # bullet entries only; the index format is "- [Title](path) — gist"
        m = re.match(r"^[-*]\s*(?:⏰\s*)?\[([^\]]+)\]\(([^)]+)\)\s*(?:[—\-:]\s*(.*))?$", ln)
        if not m:
            continue
        title = _collapse(m.group(1), 80)
        ref = m.group(2).strip()
        gist = _collapse(m.group(3) or "", 160)
        out.append({"title": title, "ref": ref, "gist": gist,
                    "type": _infer_mem_type(title, gist)})
    return out


def _infer_mem_type(title, gist):
    """Best-effort type inference from index-visible cues (the authoritative type: tag is
    in each file's frontmatter, which we deliberately do NOT open — that would be N extra
    reads for a compact index). Used only to RANK, never asserted as ground truth."""
    blob = (title + " " + gist).upper()
    if "FEEDBACK:" in blob:
        return "feedback"
    if "PROJECT" in blob:
        return "project"
    if "REFERENCE" in blob or "REFERENCE:" in blob:
        return "reference"
    return ""


def rank_memory_entries(entries):
    """Behaviourally-relevant first: feedback + project entries before reference/user/other.
    Python's sort is stable, so entries within a rank band keep their original (index)
    order — the output stays diff-friendly across regenerations."""
    rank = {"feedback": 0, "project": 1, "": 2, "user": 3, "reference": 4}
    return sorted(entries, key=lambda e: rank.get(e["type"], 2))


_TOOL_ISH_RE = re.compile(
    r"\bplugin\b|\bskill\b|\bhook\b|\bmcp\b|\bcli\b|\btool\b|\bscript\b", re.I)


def _is_tool_relevant_project(entry):
    """A `project` entry is worth keeping in the AGENT briefing only when it describes a
    plugin/tool/script/MCP the delegated agent might itself interact with or be affected
    by — the filtering signal the coordinator asked for is a judgment call layered on top
    of the type cue we already infer, not a new parsing capability. We key off keywords
    already visible in the title/gist (no extra reads): mentions of plugin/skill/hook/
    mcp/cli/tool/script. A project entry that's really a status log (e.g. a migration
    report, a photo-editing project, a ranking exercise) won't match and is dropped."""
    blob = entry["title"] + " " + entry["gist"]
    return bool(_TOOL_ISH_RE.search(blob))


def filter_memory_for_agents(entries):
    """Narrow the full MEMORY.md entry list to what a DELEGATED SUBAGENT actually needs to
    avoid repeating a known mistake or violating a tool/plugin rule:

      * type == "feedback"                       -> always kept (explicit behavioral
                                                      corrections; exactly the guardrail
                                                      a subagent needs).
      * type == "project" AND tool-relevant       -> kept (describes a plugin/tool/script
                                                      the agent might interact with).
      * type == "project" but NOT tool-relevant   -> dropped (status logs, e.g. a machine
                                                      migration report or a photo-editing
                                                      project, carry no behavioral signal).
      * type in ("user", "reference") or untyped  -> dropped entirely (about the user's
                                                      personal setup/facts, not a guardrail
                                                      a subagent needs to not violate).

    Returns entries in the SAME relative order they were given (caller ranks first)."""
    out = []
    for e in entries:
        if e["type"] == "feedback":
            out.append(e)
        elif e["type"] == "project" and _is_tool_relevant_project(e):
            out.append(e)
    return out


def cap_with_pointer(entries, limit, pointer_path):
    """Cap a list at `limit`, returning (kept, pointer_line_or_None).

    No-silent-caps: truncation must always be SAID, never silent. When entries were
    dropped, pointer_line names exactly how many and where to look for the rest; when
    nothing was dropped, pointer_line is None (nothing to announce)."""
    if len(entries) <= limit:
        return entries, None
    dropped = len(entries) - limit
    pointer = "_(%d more entr%s in %s — read it directly if the task seems related)_" % (
        dropped, "y" if dropped == 1 else "ies", pointer_path)
    return entries[:limit], pointer


# ---------------------------------------------------------------------------
# Installed-plugin scanning + nudge-text extraction
# ---------------------------------------------------------------------------

def load_installed_plugins(installed_data):
    """Return [{"name","marketplace","installPath"}] from installed_plugins.json data.
    Takes the first scope entry per plugin. Fail-safe -> []."""
    out = []
    plugins = installed_data.get("plugins")
    if not isinstance(plugins, dict):
        return out
    for key, scopes in plugins.items():
        if not scopes:
            continue
        name, _, market = key.partition("@")
        first = scopes[0] if isinstance(scopes, list) else {}
        out.append({"name": name, "marketplace": market or "",
                    "installPath": first.get("installPath") or ""})
    return out


def plugin_description(install_path):
    """.claude-plugin/plugin.json description, or '' (fail-safe)."""
    data = load_json(os.path.join(install_path, ".claude-plugin", "plugin.json"))
    return _collapse(data.get("description") or "", 240)


def _hook_scripts(install_path):
    """Absolute paths of SessionStart hook scripts referenced by hooks/hooks.json.

    Reads the command strings, resolves ${CLAUDE_PLUGIN_ROOT}/$CLAUDE_PLUGIN_ROOT to the
    install path, and returns any existing .sh/.py files named there. Fail-safe -> []."""
    hj = load_json(os.path.join(install_path, "hooks", "hooks.json"))
    hooks = (hj.get("hooks") or {}).get("SessionStart") or []
    scripts = []
    for group in hooks:
        for h in group.get("hooks", []) if isinstance(group, dict) else []:
            cmd = h.get("command", "") if isinstance(h, dict) else ""
            for m in re.finditer(r'\$\{?CLAUDE_PLUGIN_ROOT\}?(/[^"\'\s]+)', cmd):
                rel = m.group(1).lstrip("/")
                p = os.path.join(install_path, rel)
                if os.path.isfile(p):
                    scripts.append(p)
    return scripts


def extract_nudge_text(script_text, plugin_name=""):
    """Pull the literal SessionStart nudge/rule text out of a hook script body.

    Two shapes cover every haiggoh plugin observed:
      * bash:   NUDGE="<plugin>: ...."    (may span lines until the closing quote)
      * python: a string literal beginning "<plugin>: ..." passed to additionalContext
    Strategy: find the FIRST occurrence of `<name>:` inside a quoted string and return
    that string's first sentence-ish span. Returns '' if nothing parseable is found — the
    caller then falls back to the plugin.json description."""
    if not script_text:
        return ""

    # 1) bash: NUDGE="..."  (double-quoted, allowing escaped quotes inside)
    m = re.search(r'NUDGE\s*=\s*"((?:[^"\\]|\\.)*)"', script_text, re.S)
    if m:
        return _first_sentence(_unescape(m.group(1)))

    # 2) any quoted string that starts with "<plugin-name>:" — python or bash
    if plugin_name:
        pat = re.compile(r'(["\'])(' + re.escape(plugin_name) + r':\s(?:(?!\1).)*)\1', re.S)
        m = pat.search(script_text)
        if m:
            return _first_sentence(_unescape(m.group(2)))

    return ""


def _unescape(s):
    return (s.replace('\\n', ' ').replace('\\t', ' ').replace('\\"', '"')
             .replace("\\'", "'").replace('\\\\', '\\'))


def _first_sentence(s):
    """Compact a nudge to a single scannable line: keep up to the first sentence end
    (". ") if the text is long, else the whole thing, capped.

    Also guards against a MULTI-LINE python nudge whose regex capture stopped at the
    first physical string segment: such a fragment often ends dangling on a printf-style
    placeholder (`%s`) or mid-clause. We strip a trailing placeholder, and if what's left
    looks truncated (no sentence-terminal punctuation AND short), return '' so the caller
    falls back to the cleaner plugin.json description instead of shipping a stub."""
    s = _collapse(s, 100000)
    # A printf/%-format placeholder ANYWHERE means we captured only part of a formatted
    # string (e.g. a python nudge built with "...(%s)..." % (...)). Rather than ship a
    # fragment with a raw %s in it, bail so the caller falls back to the clean
    # plugin.json description. (Bash NUDGE= strings never contain %s, so this only ever
    # fires on partial python captures — exactly the case we want to reject.)
    if re.search(r'%[sdrfg]', s):
        return ""
    if not s:
        return ""
    if len(s) <= 220:
        # A short fragment that doesn't end like a finished thought is a bad capture.
        if not s.endswith((".", "!", "?", ":")) and len(s) < 80:
            return ""
        return s
    cut = s.find(". ")
    if 0 < cut < 260:
        return s[: cut + 1]
    return _collapse(s, 220)


def plugin_briefing_line(plugin, script_reader=read_text):
    """One compact briefing entry for a plugin: prefer extracted nudge text, else the
    plugin.json description. `script_reader` is injected for testability."""
    name = plugin["name"]
    path = plugin["installPath"]
    nudge = ""
    if path:
        for sp in _hook_scripts(path):
            nudge = extract_nudge_text(script_reader(sp), name)
            if nudge:
                break
    if not nudge and path:
        nudge = plugin_description(path)
    return {"name": name, "marketplace": plugin.get("marketplace", ""),
            "text": nudge, "has_nudge": bool(nudge)}


# ---------------------------------------------------------------------------
# Staleness fingerprint
# ---------------------------------------------------------------------------

def compute_fingerprint(paths):
    """Cheap change-detector: hash of (path, mtime-or-MISSING) over the SORTED input set.

    Sorted before hashing — order-independence is deliberate (mirrors no-hidden-changes'
    surfaces_fingerprint, where an unsorted stream turned harmless reorders into false
    re-arms). A path that doesn't exist contributes a stable 'MISSING' token, so a file
    appearing or disappearing flips the fingerprint too."""
    h = hashlib.sha256()
    for p in sorted(paths):
        try:
            token = str(os.stat(p).st_mtime_ns)
        except OSError:
            token = "MISSING"
        h.update(p.encode("utf-8", "replace"))
        h.update(b"\0")
        h.update(token.encode("ascii"))
        h.update(b"\n")
    return h.hexdigest()


def fingerprint_inputs(cwd, home=None):
    """The set of files whose change should trigger index regeneration:
    global CLAUDE.md, every project CLAUDE.md/AGENTS.md under cwd, the conventional
    MEMORY.md (whether or not it currently exists), and installed_plugins.json."""
    paths = [global_claude_md_path(), installed_plugins_path(),
             memory_index_path(cwd, home)]
    paths.extend(find_project_claude_mds(cwd))
    return paths


def is_stale(cwd, home=None):
    """True if the index is missing OR the current input fingerprint differs from the
    stored one. Fail-safe: any error -> True (regenerate rather than serve a stale/absent
    index)."""
    try:
        if not os.path.exists(index_output_path()):
            return True
        stored = read_text(fingerprint_path()).strip()
        current = compute_fingerprint(fingerprint_inputs(cwd, home))
        return stored != current
    except Exception:
        return True


# ---------------------------------------------------------------------------
# Index assembly
# ---------------------------------------------------------------------------

def build_index(cwd, home=None, script_reader=read_text):
    """Assemble the full agent-briefing-index.md text from live inputs.

    Pure w.r.t. its own writes — returns the string; the CLI writes it. Reads happen via
    read_text/load_json (fail-safe) so a broken input yields an empty section, not a crash."""
    home = home or os.path.expanduser("~")
    lines = []
    lines.append("# Agent briefing index")
    lines.append("")
    lines.append("Compact digest of THIS orchestrator's durable rules (CLAUDE.md, memory, "
                 "plugin nudges). A freshly-spawned subagent inherits NONE of these — paste "
                 "the relevant parts into its prompt, or tell it to read this file first, "
                 "before delegating architecture or code work. Regenerated automatically "
                 "when its sources change. Look up full detail at the cited path/name on demand.")
    lines.append("")

    # --- CLAUDE.md / AGENTS.md ---
    lines.append("## CLAUDE.md (behavioral rules — always-on)")
    lines.append("")
    gtext = read_text(global_claude_md_path())
    gsecs = scan_claude_md(gtext)
    if gsecs:
        lines.append("### ~/.claude/CLAUDE.md (global)")
        for header, gist in gsecs:
            lines.append(_fmt_section_line(header, gist))
        lines.append("")
    for pth in find_project_claude_mds(cwd):
        secs = scan_claude_md(read_text(pth))
        if not secs:
            continue
        rel = _relpath(pth, home)
        lines.append("### %s (project)" % rel)
        for header, gist in secs:
            lines.append(_fmt_section_line(header, gist))
        lines.append("")
    if not gsecs and not any(scan_claude_md(read_text(p)) for p in find_project_claude_mds(cwd)):
        lines.append("_(none found)_")
        lines.append("")

    # --- Memory (defensive: may be absent; filtered to behavioral guardrails only) ---
    lines.append("## Memory (behavioral corrections + tool/plugin notes — not everything)")
    lines.append("")
    mem_path = memory_index_path(cwd, home)
    mem_entries = parse_memory_index(read_text(mem_path)) if os.path.exists(mem_path) else []
    if mem_entries:
        ranked = rank_memory_entries(mem_entries)
        relevant = filter_memory_for_agents(ranked)
        if relevant:
            kept, pointer = cap_with_pointer(relevant, MEMORY_AGENT_LIMIT, _relpath(mem_path, home))
            lines.append(
                "From %s, filtered to what a DELEGATED subagent needs — `feedback` entries "
                "(explicit behavioral corrections) plus `project` entries about a plugin/tool/"
                "script it might touch. `user`/`reference`/status-log entries are dropped here "
                "(about you, not a guardrail); full list is in the file:" % _relpath(mem_path, home))
            for e in kept:
                tag = ("[%s] " % e["type"]) if e["type"] else ""
                detail = e["gist"] or ""
                lines.append("- %s%s (%s)%s" % (
                    tag, e["title"], e["ref"], (" — " + detail) if detail else ""))
            if pointer:
                lines.append(pointer)
            lines.append("")
        else:
            lines.append("_(memory index has no feedback/tool-relevant-project entries — "
                         "skipped; see %s for everything else)_" % _relpath(mem_path, home))
            lines.append("")
    else:
        lines.append("_(no memory index at the conventional path — skipped)_")
        lines.append("")

    # --- Plugins (highest-value: literal nudge text) ---
    lines.append("## Installed-plugin rules (SessionStart nudges — the actual rule text)")
    lines.append("")
    installed = load_installed_plugins(load_json(installed_plugins_path()))
    plugin_lines = []
    for p in sorted(installed, key=lambda x: x["name"]):
        bl = plugin_briefing_line(p, script_reader=script_reader)
        if bl["text"]:
            plugin_lines.append(bl)
    if plugin_lines:
        lines.append("Each subagent starts unaware of these. The text is the literal nudge "
                     "where extractable, else the plugin's description:")
        for bl in plugin_lines:
            lines.append("- **%s**: %s" % (bl["name"], bl["text"]))
        lines.append("")
    else:
        lines.append("_(no plugin nudges found)_")
        lines.append("")

    lines.append("---")
    lines.append("_Generated by brief-agents. Do not hand-edit; it is regenerated when "
                 "CLAUDE.md / memory / installed plugins change._")
    return "\n".join(lines) + "\n"


def _fmt_section_line(header, gist):
    return "- **%s**%s" % (header, (" — " + gist) if gist else "")


def _relpath(path, home):
    """Display path with ~ for home, for portability across machines/users."""
    home = home.rstrip("/")
    if path.startswith(home + "/"):
        return "~" + path[len(home):]
    return path


# ---------------------------------------------------------------------------
# Atomic writes (CLI helpers; kept here so tests can exercise them without a shell)
# ---------------------------------------------------------------------------

def _atomic_write(path, text):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def generate(cwd, home=None, script_reader=read_text):
    """Build + write the index AND stamp the fingerprint. Returns the index path."""
    home = home or os.path.expanduser("~")
    text = build_index(cwd, home=home, script_reader=script_reader)
    _atomic_write(index_output_path(), text)
    _atomic_write(fingerprint_path(), compute_fingerprint(fingerprint_inputs(cwd, home)))
    return index_output_path()
