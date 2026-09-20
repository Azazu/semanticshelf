#!/bin/sh
# Mechanical pre-gate floor (lean adaptation of narrative-forge's
# pregate-verify.sh). Runs before a reviewer is ever invoked, so the
# reviewer's round is never spent repeating what a script already knows.
# Aggregates every check; exits non-zero only on FAIL — WARN never does.
#
# Usage: pregate-verify.sh <gate1|gate2> <change-id>
# Exit:  0 all checks passed · 1 any FAIL · 2 usage / prerequisites
set -u

ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || { echo 'pregate-verify: not inside a git repository' >&2; exit 2; }
cd "$ROOT" || exit 2
MODE=${1:-}; ID=${2:-}
case "$MODE" in gate1|gate2) ;; *) MODE="" ;; esac
[ -n "$MODE" ] && [ -n "$ID" ] || { printf 'usage: %s <gate1|gate2> <change-id>\n' "$0" >&2; exit 2; }
command -v python3 >/dev/null 2>&1 || { echo 'pregate-verify: python3 is required' >&2; exit 2; }

DIR="openspec/changes/$ID"
FAILURES=0; WARNINGS=0
ok()   { printf '[OK]   %s\n' "$1"; }
fail() { printf '[FAIL] %s\n       hint: %s\n' "$1" "$2"; FAILURES=$((FAILURES + 1)); }
warn() { printf '[WARN] %s\n' "$1"; WARNINGS=$((WARNINGS + 1)); }

[ -d "$DIR" ] || fail "change directory $DIR missing" "wrong id, or already archived"

# 1. whitespace hygiene over the branch diff
if git diff --check main...HEAD >/dev/null 2>&1; then ok "git diff --check clean"
else fail "git diff --check reports whitespace errors" "fix trailing whitespace / conflict markers"; fi

# 2. strict OpenSpec validation
if command -v openspec >/dev/null 2>&1; then
  if openspec validate "$ID" --strict >/dev/null 2>&1; then ok "openspec validate $ID --strict"
  else fail "openspec validate $ID --strict fails" "openspec validate $ID --strict  (see its output)"; fi
else fail "openspec CLI not installed" "npm install -g @fission-ai/openspec"; fi

# 3. proposal: risk tier and non-goals
TIER=""
if [ -f "$DIR/proposal.md" ]; then
  TIER=$(grep -E -m1 '^\*\*Risk-Tier:\*\* *(low|medium|high) *$' "$DIR/proposal.md" | sed -E 's/.*(low|medium|high).*/\1/')
  [ -n "$TIER" ] && ok "risk tier declared: $TIER" || fail "proposal.md has no valid Risk-Tier" "add a line: **Risk-Tier:** low|medium|high"
  grep -E -q -i '^## *Non-goals' "$DIR/proposal.md" && ok "proposal.md has a Non-goals section" || fail "proposal.md lacks '## Non-goals'" "state what the change deliberately does not do"
else fail "proposal.md missing" "run /opsx:propose"; fi

# 4. high tier, gate 1: the applicability table exists in design.md
if [ "$MODE" = gate1 ] && [ "$TIER" = high ]; then
  if [ -f "$DIR/design.md" ] && grep -E -q -i 'applicability' "$DIR/design.md"; then ok "design.md carries the applicability table (high tier)"
  else fail "high tier without an applicability table in design.md" "add the triggered failure questions (AGENTS.md, Definition of Ready)"; fi
fi

# 5. tasks: present; at gate 2 all checked
if [ -f "$DIR/tasks.md" ]; then
  total=$(grep -c '^- \[[ x]\] ' "$DIR/tasks.md" || true); open=$(grep -c '^- \[ \] ' "$DIR/tasks.md" || true)
  [ "${total:-0}" -gt 0 ] && ok "tasks.md has $total task(s)" || fail "tasks.md has no tasks" "a change with nothing to do is not a change"
  if [ "$MODE" = gate2 ]; then
    [ "${open:-0}" -eq 0 ] && ok "every task checked" || fail "$open task(s) still unchecked at gate 2" "finish or descope them before requesting Gate 2"
  fi
else fail "tasks.md missing" "run /opsx:propose"; fi

# 6. content checks (python3): checked-task paths exist; markdown links resolve
PYOUT=$(python3 - "$MODE" "$DIR" <<'PY'
import os, re, subprocess, sys
mode, d = sys.argv[1], sys.argv[2]
out = []
def sh(c): return subprocess.run(c, shell=True, capture_output=True, text=True).stdout
changed = sorted(set(l for l in (sh("git diff main...HEAD --name-only") + sh("git status --porcelain | cut -c4-")).splitlines() if l))
changed_md = [f for f in changed if f.endswith(".md") and os.path.isfile(f)]

# checked tasks: every backticked path they name must exist (repo- or change-relative)
tasks = os.path.join(d, "tasks.md"); bad = []
if os.path.isfile(tasks):
    block, blocks = None, []
    for line in open(tasks, encoding="utf-8"):
        m = re.match(r"^- \[(x| )\] ", line)
        if m:
            if block: blocks.append(block)
            block = line if m.group(1) == "x" else None
        elif block is not None and (line.startswith("  ") or not line.strip()):
            block += line
    if block: blocks.append(block)
    path_re = re.compile(r"`([\w./-]+/[\w./-]+|[\w-]+\.(?:sh|md|py|php|yml|yaml|json|toml|env|sql))`")
    for b in blocks:
        for p in path_re.findall(b):
            if p.startswith("<") or "*" in p: continue
            if not (os.path.exists(p) or os.path.exists(os.path.join(d, p))): bad.append(p)
if bad: out.append(("FAIL", "checked-task referenced paths missing: " + " ".join(sorted(set(bad))), "outputs must exist before a task is [x]"))
else: out.append(("OK", "checked-task referenced paths exist", ""))

# markdown links in changed files
badl, absl = [], []
for f in changed_md:
    text = re.sub(r"`[^`]*`", "", open(f, encoding="utf-8").read())
    for m in re.finditer(r"\]\(<?([^)>#\s]+)", text):
        t = m.group(1)
        if re.match(r"^(https?:|mailto:)", t): continue
        if t.startswith("/"): absl.append(f"{f}: {t}"); continue
        if not os.path.exists(os.path.normpath(os.path.join(os.path.dirname(f), re.sub(r":\d+$", "", t)))): badl.append(f"{f}: {t}")
if absl: out.append(("FAIL", "absolute filesystem links: " + "; ".join(absl[:5]), "use repository-relative references"))
if badl: out.append(("FAIL", "unresolved relative links: " + "; ".join(badl[:5]), "fix the target path"))
if not absl and not badl: out.append(("OK", f"markdown links resolve ({len(changed_md)} changed .md files)", ""))

for lvl, msg, hint in out: print(f"{lvl}\t{msg}\t{hint}")
print("__PREGATE_END__")
PY
) ; PYRC=$?
printf '%s\n' "$PYOUT" | grep -v '^__PREGATE_END__$' | while IFS="$(printf '\t')" read -r lvl msg hint; do
  case "$lvl" in OK) ok "$msg" ;; WARN) warn "$msg" ;; FAIL) fail "$msg" "$hint" ;; esac
done
if [ "$PYRC" -ne 0 ] || ! printf '%s\n' "$PYOUT" | grep -qx '__PREGATE_END__'; then
  fail "content checker did not complete (python exit $PYRC)" "treat this run as failed and fix pregate-verify.sh"
fi
FAILURES=$((FAILURES + $(printf '%s\n' "$PYOUT" | grep -c '^FAIL' || true)))

# 7. gate 2: the project's own check suite must be green
if [ "$MODE" = gate2 ]; then
  if [ -f Makefile ] && grep -E -q '^check:' Makefile; then
    if OUT=$(make check 2>&1); then ok "make check green"
    else fail "make check fails" "fix lint/static-analysis/tests before requesting Gate 2"; printf '%s\n' "$OUT" | tail -15 | sed 's/^/       /'; fi
  else fail "Makefile has no 'check' target" "define check: lint + static analysis + tests (AGENTS.md Stack section)"; fi
fi

if [ "$FAILURES" -eq 0 ]; then printf 'pregate-verify: %s %s — all checks passed (%d warning(s))\n' "$MODE" "$ID" "$WARNINGS"; exit 0
else printf 'pregate-verify: %s %s — %d check(s) FAILED (%d warning(s))\n' "$MODE" "$ID" "$FAILURES" "$WARNINGS"; exit 1; fi
