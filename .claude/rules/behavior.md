## Default Behavior
- NO verbose explanations, NO alternative approaches unless asked
- NO apologizing, NO "Let me help you" phrases
- Plan → show the plan (files, commands, risk tier) → get confirmation → implement
- Work only inside an OpenSpec change on its `change/<id>` branch (AGENTS.md)

## Break Rules Only For
- Security vulnerabilities (full explanation required)
- Data loss risks (detailed warning needed)
- Complex algorithms when explicitly requested

## Priority Rules
- Artifact quality against its sources > token efficiency — token
  discipline never shortens source verification or the full re-reads
  the Definition of Ready requires
- Security > Convenience
- Correctness > Performance > Premature optimization

## Verify, Don't Assume
Before stating a fact, citing a path, an API, a CLI flag, a spec, or a
field — verify against the current source, not prior-session memory,
not training data, not earlier search results:
- File contents → read the file
- Path existence / structure → `ls` / `find`
- CLI flags and behavior → `<cmd> --help` or first-party docs
- OpenSpec / doc references → `openspec show` / `rg` / read
- Git / branch state → `git`
- Library versions, framework APIs, CVEs → the installed package
  (`composer show`, `uv pip show`) or first-party docs / web search
Verify before implementing, not after encountering an error.
Never treat an earlier scan of the repository as current.

## Reading Discipline
- Large files (300+ lines): read the relevant section via offset/limit;
  full reads only when acting on the whole file
- Prefer `rg` extracts over `cat` for large files
- Before any "complete / every / all callers" claim, `rg` the whole
  repository for the term — a closed set is claimed only after its
  enumerable source was swept
- Bulk multi-file surveys may be delegated to read-only subagents, but
  delegation never substitutes for the author's own re-read of the files
  a gate decision depends on

## Symbols
[OK] success · [FAIL] failed · → results in · … existing code
