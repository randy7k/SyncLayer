"""Agent data shared by the brand generator and the sync test (standard library only).

Mirrors agents/*.md and the catalog in rules/agentes.md; tests/test_brand_agents.py
fails if name, model, tools or the guard drift apart.
"""

# name, role (English copy), model, tools, writes (None = no Edit/Write; else the scope of
# the role, not a guarantee), guarded Bash
# Classified by tools, not by guarantee: the guard is a heuristic, not a sandbox.
AGENTS = [
    ("heimdall", "Maps an unfamiliar repo or area", "haiku", "Read, Grep, Glob", None, False),
    ("hermes", "Checks official docs and libraries", "sonnet", "WebSearch, WebFetch, Read, Grep, Glob", None, False),
    ("atlas", "Plans and designs the change", "claude-fable-5-2", "Read, Grep, Glob, Write", "plan", False),
    ("sindri", "Implements one unit of work", "sonnet", "Read, Edit, Write, Grep, Glob, Bash", "code and its tests", False),
    ("anubis", "Runs and extends the tests", "sonnet", "Read, Grep, Glob, Bash, Edit, Write", "tests", True),
    ("salomon", "Reviews the diff, independently", "opus", "Read, Grep, Glob, Bash", None, True),
    ("hector", "Reviews the diff for security", "opus", "Read, Grep, Glob, Bash", None, True),
    ("sherlock", "Finds the root cause of a failure", "opus", "Read, Grep, Glob, Bash", None, True),
    ("shakespeare", "Keeps the project docs current", "sonnet", "Read, Grep, Glob, Edit, Write", "docs", False),
]
