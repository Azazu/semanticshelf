#!/bin/sh
# Fixture suite for scripts/workflow-verify.sh: throwaway git repos, a
# stubbed `openspec` on PATH, one demonstrated failing input per rule.
# A verifier nobody has seen fail proves nothing (narrative-forge class A).
# Usage: scripts/workflow_verify_test.sh ; exit non-zero on any failing case.
set -u
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
V="$HERE/workflow-verify.sh"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
PASS=0; FAILED=0
t()  { if "$@" >/dev/null 2>&1; then PASS=$((PASS+1)); else FAILED=$((FAILED+1)); printf 'FAIL: %s\n' "$*"; fi; }
tn() { if "$@" >/dev/null 2>&1; then FAILED=$((FAILED+1)); printf 'FAIL (expected non-zero): %s\n' "$*"; else PASS=$((PASS+1)); fi; }
teq(){ exp=$1; shift; got=$("$@" 2>/dev/null); if [ "$got" = "$exp" ]; then PASS=$((PASS+1)); else FAILED=$((FAILED+1)); printf 'FAIL: %s\n  expected: %s\n  got:      %s\n' "$*" "$exp" "$got"; fi; }

# stub openspec: always valid
mkdir -p "$TMP/bin"; printf '#!/bin/sh\nexit 0\n' > "$TMP/bin/openspec"; chmod +x "$TMP/bin/openspec"; PATH="$TMP/bin:$PATH"

R="$TMP/repo"; mkdir -p "$R"; cd "$R"
git init -q -b main . ; git config user.email t@t; git config user.name t
git commit -q --allow-empty -m init
SHA1=$(git rev-parse HEAD); SHA2=1111111111111111111111111111111111111111

# --- decision --------------------------------------------------------
F="$TMP/r.md"
: > "$F";                                    tn "$V" decision "$F" 1
cat > "$F" <<EOF
# Review — x

## Round 1 · Gate 1
**Reviewer:** codex
**Reviewed-Commit:** $SHA1
**Verdict:** approved
EOF
teq "Round approved $SHA1" "$V" decision "$F" 1
tn "$V" decision "$F" 2                       # a gate-1 round never answers for gate 2
cat >> "$F" <<EOF

## Round 1 · Gate 2
**Reviewed-Commit:** $SHA1
**Verdict:** changes-requested

### Findings
| # | Severity | Location | Finding | Status |
|---|---|---|---|---|
| 1 | major | a.md | bad | open |

## Confirmation 1 · Gate 2 · Round 1
**Reviewed-Commit:** $SHA2
**Verdict:** confirmed
EOF
teq "Confirmation confirmed $SHA2" "$V" decision "$F" 2   # the LAST record decides
cat >> "$F" <<EOF

## Waiver · Gate 2
**Granted-by:** user
**Commit:** $SHA2
**Verdict:** waived
EOF
teq "Waiver waived $SHA2" "$V" decision "$F" 2

# --- tier ------------------------------------------------------------
P="$TMP/p.md"; printf '# P\n' > "$P";        tn "$V" tier "$P"
printf '# P\n\n**Risk-Tier:** medium\n' > "$P"; teq medium "$V" tier "$P"
printf '**Risk-Tier:** urgent\n' > "$P";      tn "$V" tier "$P"   # outside the closed set

# --- mode ------------------------------------------------------------
teq auto "$V" mode                                          # no AGENTS.md → auto
printf '# Rules\n\n**Review mode:** manual\n' > AGENTS.md;    teq manual "$V" mode
printf '# Rules\n\n**Review mode:** sometimes\n' > AGENTS.md; teq auto "$V" mode   # outside the closed set → auto
rm -f AGENTS.md

# --- merge, end to end -----------------------------------------------
mkchange() { # $1 tier
  mkdir -p openspec/changes/c
  printf '# c\n\n**Risk-Tier:** %s\n\n## Non-goals\n- none\n' "$1" > openspec/changes/c/proposal.md
  printf '# Tasks\n- [x] 1.1 done\n' > openspec/changes/c/tasks.md
  printf '# Handoff\n\n**State:** ready-to-merge\n**Branch:** change/c\n' > openspec/changes/c/handoff.md
  git add -A; git commit -q -m "feat(c): work"
}
git checkout -q -b change/c; mkchange low
t  "$V" merge c                                             # low tier: no gate needed
printf '# Tasks\n- [ ] 1.1 not done\n' > openspec/changes/c/tasks.md; git commit -q -am "wip"
tn "$V" merge c                                             # unchecked task blocks
git reset -q --hard HEAD~1
git checkout -q main; tn "$V" merge nosuch                  # unknown change
git checkout -q change/c
# medium tier without any gate 2 record
sed -i 's/low/medium/' openspec/changes/c/proposal.md; git commit -q -am "tier medium"
tn "$V" merge c
# gate 2 approved and fresh
H=$(git rev-parse HEAD)
printf '# Review — c\n\n## Round 1 · Gate 2\n**Reviewed-Commit:** %s\n**Verdict:** approved\n' "$H" > openspec/changes/c/review.md
git add -A; git commit -q -m "review: gate 2 full — approved (c)"
t  "$V" merge c                                             # only review.md changed since -> fresh
printf '\nx\n' >> openspec/changes/c/proposal.md; git commit -q -am "docs: touch proposal"
tn "$V" merge c                                             # a non-protocol file changed -> stale
git reset -q --hard HEAD~1
sed -i 's/approved/changes-requested/' openspec/changes/c/review.md; git commit -q -am "review: cr"
tn "$V" merge c                                             # changes-requested blocks
git reset -q --hard HEAD~1
printf '\n### Findings\n| # | Severity | Location | Finding | Status |\n|---|---|---|---|---|\n| 1 | minor | a | b | open |\n' >> openspec/changes/c/review.md; git commit -q -am "review: open finding"
tn "$V" merge c                                             # an open finding blocks even under approved
git reset -q --hard HEAD~1
sed -i 's/ready-to-merge/implementing/' openspec/changes/c/handoff.md; git commit -q -am "handoff"
tn "$V" merge c                                             # wrong handoff state blocks
git reset -q --hard HEAD~1

# --- apply -----------------------------------------------------------
t  "$V" apply c                                             # medium: gate 1 not required
sed -i 's/medium/high/' openspec/changes/c/proposal.md; git commit -q -am "tier high"
tn "$V" apply c                                             # high without gate 1 record blocks
printf '\n## Round 1 · Gate 1\n**Reviewed-Commit:** %s\n**Verdict:** approved\n' "$(git rev-parse HEAD)" >> openspec/changes/c/review.md; git commit -q -am "review: g1"
t  "$V" apply c

printf 'workflow_verify_test: %d passed, %d failed\n' "$PASS" "$FAILED"
[ "$FAILED" -eq 0 ]
