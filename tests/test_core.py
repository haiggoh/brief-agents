#!/usr/bin/env python3
"""Framework-free unit tests for brief_agents_core: scanning, nudge extraction, memory
parsing, ranking, the staleness fingerprint, and full index assembly.

Run: python3 tests/test_core.py    (exit 0 = all pass; nonzero = failure)
No third-party deps — pure stdlib, so it runs directly against the source files."""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "bin"))
import brief_agents_core as core  # noqa: E402

_fails = []


def check(cond, msg):
    if cond:
        print("  ok:", msg)
    else:
        print("  FAIL:", msg)
        _fails.append(msg)


# --------------------------------------------------------------------------
# scan_claude_md
# --------------------------------------------------------------------------
def test_scan_claude_md():
    print("scan_claude_md")
    body = (
        "# Global instructions\n\n"
        "## Verify before asserting a limitation\n\n"
        "Before telling the user something is unavailable, check the source first.\n\n"
        "## Web search\n\n"
        "Native WebSearch does not work on this machine.\n"
        "### Sub detail\n\n"
        "> a quoted gist line\n"
    )
    secs = core.scan_claude_md(body)
    headers = [h for h, _ in secs]
    check("Verify before asserting a limitation" in headers, "captures ## headers")
    check("Web search" in headers, "captures multiple headers")
    check("Sub detail" in headers, "captures ### headers too")
    gist = dict(secs)["Verify before asserting a limitation"]
    check(gist.startswith("Before telling"), "pulls one-line gist after header")
    check(dict(secs)["Sub detail"] == "a quoted gist line", "strips quote marker in gist")
    check(core.scan_claude_md("") == [], "empty text -> []")
    check(core.scan_claude_md("no headers here at all") == [], "headerless -> []")


# --------------------------------------------------------------------------
# extract_nudge_text
# --------------------------------------------------------------------------
def test_extract_nudge_bash():
    print("extract_nudge_text (bash NUDGE=)")
    script = (
        '#!/usr/bin/env bash\nset -uo pipefail\n'
        'NUDGE="measure-twice: before building durable automation STOP and consult the '
        'skill. Two checks first."\n'
        'printf "%s" "$NUDGE"\n'
    )
    txt = core.extract_nudge_text(script, "measure-twice")
    check(txt.startswith("measure-twice:"), "extracts bash NUDGE= text")
    check("consult the" in txt, "keeps the rule body")


def test_extract_nudge_python():
    print("extract_nudge_text (python string literal)")
    script = (
        'ctx = ("resume-interrupted: your most recent session appears interrupted; '
        'offer to resume. More detail follows.")\n'
        'print(json.dumps({"additionalContext": ctx}))\n'
    )
    txt = core.extract_nudge_text(script, "resume-interrupted")
    check(txt.startswith("resume-interrupted:"), "extracts python nudge by <name>: prefix")


def test_extract_nudge_fallback():
    print("extract_nudge_text (no match)")
    check(core.extract_nudge_text("", "x") == "", "empty script -> ''")
    check(core.extract_nudge_text("echo hi", "measure-twice") == "",
          "no nudge string -> '' (caller falls back to description)")


def test_extract_nudge_truncated_fragment():
    print("extract_nudge_text (truncated python fragment with %s)")
    # mimics resume-interrupted: a multi-line concatenated string whose first physical
    # segment ends dangling on a %s placeholder — should be rejected -> fallback.
    script = (
        'ctx = ("resume-interrupted: your most recent substantive session (%s) appears to have been "\n'
        '       "interrupted mid-task; offer to pick up where it left off." % (ts,))\n'
    )
    txt = core.extract_nudge_text(script, "resume-interrupted")
    check(txt == "", "fragment containing %s rejected so caller falls back to description")


# --------------------------------------------------------------------------
# memory index parsing + ranking
# --------------------------------------------------------------------------
def test_parse_memory_index():
    print("parse_memory_index")
    body = (
        "# Memory Index\n\n"
        "- [Some Project](proj.md) — PROJECT: builds a thing; status open\n"
        "- [A gotcha](gotcha.md) — FEEDBACK: do X not Y\n"
        "- ⏰ [A reminder](rem.md) — REFERENCE: recognize the wifi\n"
        "not a bullet line\n"
    )
    entries = core.parse_memory_index(body)
    check(len(entries) == 3, "parses 3 bullet entries, ignores non-bullets")
    check(entries[0]["ref"] == "proj.md", "captures file ref")
    check(entries[0]["type"] == "project", "infers project type")
    check(entries[1]["type"] == "feedback", "infers feedback type")
    check(entries[2]["type"] == "reference", "infers reference type, tolerates ⏰ prefix")
    check(core.parse_memory_index("") == [], "empty -> []")


def test_rank_memory_entries():
    print("rank_memory_entries")
    entries = [
        {"title": "r", "ref": "r.md", "gist": "", "type": "reference"},
        {"title": "f", "ref": "f.md", "gist": "", "type": "feedback"},
        {"title": "p", "ref": "p.md", "gist": "", "type": "project"},
        {"title": "u", "ref": "u.md", "gist": "", "type": "user"},
    ]
    ranked = [e["type"] for e in core.rank_memory_entries(entries)]
    check(ranked[0] == "feedback" and ranked[1] == "project",
          "feedback+project ranked before reference/user")
    check(ranked.index("reference") > ranked.index("user"),
          "reference ranked last")


# --------------------------------------------------------------------------
# fingerprint / staleness
# --------------------------------------------------------------------------
def test_fingerprint():
    print("compute_fingerprint")
    with tempfile.TemporaryDirectory() as d:
        a = os.path.join(d, "a"); b = os.path.join(d, "b")
        open(a, "w").write("x"); open(b, "w").write("y")
        f1 = core.compute_fingerprint([a, b])
        f2 = core.compute_fingerprint([b, a])
        check(f1 == f2, "order-independent (sorted before hashing)")
        missing = os.path.join(d, "nope")
        fm1 = core.compute_fingerprint([a, missing])
        check(len(fm1) == 64, "missing file contributes a stable token, no crash")
        # touch a to change mtime
        import time
        time.sleep(0.01)
        os.utime(a, None)
        f3 = core.compute_fingerprint([a, b])
        check(f3 != f1, "mtime change flips the fingerprint")
        # a file appearing flips it too
        open(missing, "w").write("z")
        fm2 = core.compute_fingerprint([a, missing])
        check(fm2 != fm1, "a file appearing flips the fingerprint")


def test_is_stale():
    print("is_stale")
    with tempfile.TemporaryDirectory() as d:
        idx = os.path.join(d, "index.md")
        fp = os.path.join(d, "fp")
        src = os.path.join(d, "CLAUDE.md")
        open(src, "w").write("# t\n## H\ngist\n")
        os.environ["BRIEF_AGENTS_INDEX_FILE"] = idx
        os.environ["BRIEF_AGENTS_FINGERPRINT_FILE"] = fp
        os.environ["BRIEF_AGENTS_GLOBAL_CLAUDE_MD"] = src
        os.environ["BRIEF_AGENTS_INSTALLED_PLUGINS_FILE"] = os.path.join(d, "ip.json")
        os.environ["BRIEF_AGENTS_MEMORY_INDEX_FILE"] = os.path.join(d, "MEMORY.md")
        try:
            check(core.is_stale(d) is True, "missing index -> stale")
            core.generate(d)
            check(core.is_stale(d) is False, "fresh after generate")
            import time; time.sleep(0.01); os.utime(src, None)
            check(core.is_stale(d) is True, "source mtime change -> stale again")
        finally:
            for k in ("BRIEF_AGENTS_INDEX_FILE", "BRIEF_AGENTS_FINGERPRINT_FILE",
                      "BRIEF_AGENTS_GLOBAL_CLAUDE_MD", "BRIEF_AGENTS_INSTALLED_PLUGINS_FILE",
                      "BRIEF_AGENTS_MEMORY_INDEX_FILE"):
                os.environ.pop(k, None)


# --------------------------------------------------------------------------
# load_installed_plugins + plugin_briefing_line
# --------------------------------------------------------------------------
def test_load_installed_plugins():
    print("load_installed_plugins")
    data = {"plugins": {
        "foo@haiggoh": [{"installPath": "/x/foo"}],
        "bar@official": [{"installPath": "/x/bar"}],
    }}
    got = core.load_installed_plugins(data)
    names = sorted(p["name"] for p in got)
    check(names == ["bar", "foo"], "extracts all plugin names")
    check(core.load_installed_plugins({}) == [], "malformed -> []")


def test_plugin_briefing_line():
    print("plugin_briefing_line")
    # fake a plugin whose hook script has a NUDGE, via injected script_reader
    with tempfile.TemporaryDirectory() as d:
        pdir = os.path.join(d, "p")
        os.makedirs(os.path.join(pdir, "hooks"))
        os.makedirs(os.path.join(pdir, ".claude-plugin"))
        open(os.path.join(pdir, "hooks", "hooks.json"), "w").write(
            '{"hooks":{"SessionStart":[{"hooks":[{"type":"command",'
            '"command":"bash \\"${CLAUDE_PLUGIN_ROOT}/hooks/nudge.sh\\""}]}]}}')
        open(os.path.join(pdir, "hooks", "nudge.sh"), "w").write(
            'NUDGE="demo-plugin: do the thing before the other thing."\n')
        open(os.path.join(pdir, ".claude-plugin", "plugin.json"), "w").write(
            '{"description":"fallback desc"}')
        bl = core.plugin_briefing_line(
            {"name": "demo-plugin", "installPath": pdir, "marketplace": "haiggoh"})
        check(bl["text"].startswith("demo-plugin:"), "prefers extracted nudge text")
        check(bl["has_nudge"] is True, "flags nudge present")

        # a plugin with no hook falls back to description
        pdir2 = os.path.join(d, "q")
        os.makedirs(os.path.join(pdir2, ".claude-plugin"))
        open(os.path.join(pdir2, ".claude-plugin", "plugin.json"), "w").write(
            '{"description":"just a description"}')
        bl2 = core.plugin_briefing_line({"name": "q", "installPath": pdir2})
        check(bl2["text"] == "just a description", "falls back to plugin.json description")


# --------------------------------------------------------------------------
# build_index end-to-end (memory present AND absent)
# --------------------------------------------------------------------------
def test_build_index():
    print("build_index")
    with tempfile.TemporaryDirectory() as home:
        cwd = os.path.join(home, "proj")
        os.makedirs(cwd)
        gclaude = os.path.join(home, ".claude", "CLAUDE.md")
        os.makedirs(os.path.dirname(gclaude))
        open(gclaude, "w").write("# G\n## Rule one\nthe gist of rule one\n")
        # project CLAUDE.md
        open(os.path.join(cwd, "CLAUDE.md"), "w").write("# P\n## Proj rule\nproj gist\n")
        ip = os.path.join(home, ".claude", "plugins", "installed_plugins.json")
        os.makedirs(os.path.dirname(ip))
        open(ip, "w").write('{"plugins":{}}')

        os.environ["BRIEF_AGENTS_GLOBAL_CLAUDE_MD"] = gclaude
        os.environ["BRIEF_AGENTS_INSTALLED_PLUGINS_FILE"] = ip
        try:
            # memory ABSENT -> defensively skipped, no crash
            os.environ["BRIEF_AGENTS_MEMORY_INDEX_FILE"] = os.path.join(home, "nope", "MEMORY.md")
            txt = core.build_index(cwd, home=home)
            check("Rule one" in txt, "includes global CLAUDE.md section header")
            check("Proj rule" in txt, "includes project CLAUDE.md section header")
            check("no memory index" in txt.lower(), "memory absent -> skipped note, no crash")

            # memory PRESENT
            mem = os.path.join(home, "mem", "MEMORY.md")
            os.makedirs(os.path.dirname(mem))
            open(mem, "w").write("# Memory Index\n- [Thing](t.md) — FEEDBACK: do X\n")
            os.environ["BRIEF_AGENTS_MEMORY_INDEX_FILE"] = mem
            txt2 = core.build_index(cwd, home=home)
            check("Thing" in txt2 and "t.md" in txt2, "includes memory entry + file pointer")
            check("~/" in txt2, "paths shown with ~ for portability")
        finally:
            for k in ("BRIEF_AGENTS_GLOBAL_CLAUDE_MD", "BRIEF_AGENTS_INSTALLED_PLUGINS_FILE",
                      "BRIEF_AGENTS_MEMORY_INDEX_FILE"):
                os.environ.pop(k, None)


def test_cwd_slug():
    print("cwd_slug")
    check(core.cwd_slug("/Users/bra0002h") == "-Users-bra0002h", "slugs / to -")
    check(core.cwd_slug("/a/b.c") == "-a-b-c", "slugs . to - as well")


def main():
    for fn in (test_scan_claude_md, test_extract_nudge_bash, test_extract_nudge_python,
               test_extract_nudge_fallback, test_extract_nudge_truncated_fragment,
               test_parse_memory_index, test_rank_memory_entries,
               test_fingerprint, test_is_stale, test_load_installed_plugins,
               test_plugin_briefing_line, test_build_index, test_cwd_slug):
        fn()
    if _fails:
        print("\nFAILURES: %d" % len(_fails))
        return 1
    print("\nALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
