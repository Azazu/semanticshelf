#!/bin/sh
# Read-only workflow verifier for the AGENTS.md lifecycle.
# Lean adaptation of narrative-forge's verifier (ADR-015/ADR-080): the
# LAST decision record of a gate decides; Gate 2 has a freshness rule,
# Gate 1 deliberately has none (design edits describing the
# implementation must not cascade into a Gate 1 reopen).
#
# Usage:
#   workflow-verify.sh apply    <change-id>          may implementation start?
#   workflow-verify.sh merge    <change-id>          may change/<id> be merged into main?
#   workflow-verify.sh archive  <change-id>          may the change be archived?
#   workflow-verify.sh decision <review-file> <gate> print "<kind> <verdict> <commit>" of the
#                                                    gate's last record (Round|Confirmation|Waiver);
#                                                    exit 1 when the gate has none
#   workflow-verify.sh tier     <proposal-file>      print low|medium|high; exit 1 if undeclared
#   workflow-verify.sh mode                          print the review mode from AGENTS.md
#                                                    (auto|manual; absent = auto)
#
# Exit: 0 every check passed · 1 any FAIL · 2 usage / not a git repository
set -u

ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || { echo 'workflow-verify: not inside a git repository' >&2; exit 2; }
cd "$ROOT" || exit 2
FAILURES=0
ok()   { printf '[OK]   %s\n' "$1"; }
fail() { printf '[FAIL] %s\n       hint: %s\n' "$1" "$2"; FAILURES=$((FAILURES + 1)); }
note() { printf '[NOTE] %s\n' "$1"; }
usage(){ sed -n '2,20p' "$0" >&2; exit 2; }

PROTOCOL_FILES='review.md handoff.md tasks.md'

decision() { # $1 = review file, $2 = gate
  awk -v gate="$2" '
    function flush(){ if (k != "") last = k " " (v == "" ? "-" : v) " " (c == "" ? "-" : c) }
    /^## / { flush(); k = ""; v = ""; c = ""
      if ($0 ~ ("^## Round [0-9]+ · Gate " gate " *$")) k = "Round"
      else if ($0 ~ ("^## Confirmation [0-9]+ · Gate " gate " · Round [0-9]+ *$")) k = "Confirmation"
      else if ($0 ~ ("^## Waiver · Gate " gate " *$")) k = "Waiver"
      next }
    k != "" && /^\*\*Verdict:\*\*/ { v = $0; sub(/^\*\*Verdict:\*\* */, "", v); sub(/ *$/, "", v) }
    k != "" && /^\*\*Reviewed-Commit:\*\*/ { c = $NF }
    k != "" && /^\*\*Commit:\*\*/ { if (c == "") c = $NF }
    END { flush(); if (last != "") print last; else exit 1 }' "$1"
}

tier() { # $1 = proposal file
  grep -E -m1 '^\*\*Risk-Tier:\*\* *(low|medium|high) *$' "$1" 2>/dev/null \
    | sed -E 's/^\*\*Risk-Tier:\*\* *(low|medium|high) *$/\1/'
}

passes() { case "$1" in approved|confirmed|waived) return 0 ;; *) return 1 ;; esac; }

mode() { # review mode declared in AGENTS.md; auto when absent
  m=$(grep -E -m1 '^\*\*Review mode:\*\* *(auto|manual) *$' AGENTS.md 2>/dev/null | sed -E 's/^\*\*Review mode:\*\* *//; s/ *$//')
  printf '%s\n' "${m:-auto}"
}

# Gate check over a review file. $1 file, $2 gate, $3 label, $4 fresh-against ref ("" = no freshness)
check_gate() {
  rec=$(decision "$1" "$2") || { fail "$3: no decision record for gate $2" "run /gate-review <id> $2"; return; }
  kind=${rec%% *}; rest=${rec#* }; verdict=${rest%% *}; commit=${rest#* }
  if passes "$verdict"; then ok "$3: gate $2 $kind $verdict ($commit)"; else fail "$3: gate $2 last record is $kind $verdict" "fix findings and request a confirmation"; return; fi
  if [ -n "$4" ] && [ "$commit" != "-" ]; then
    stale=$(git diff --name-only "$commit" "$4" 2>/dev/null | while IFS= read -r p; do
      b=${p##*/}; case " $PROTOCOL_FILES " in *" $b "*) [ "${p#openspec/changes/}" != "$p" ] && continue ;; esac; printf '%s\n' "$p"; done)
    if [ -z "$stale" ]; then ok "$3: gate $2 decision is fresh (only protocol files changed since $commit)"
    else fail "$3: gate $2 decision at $commit is stale — changed since: $(printf '%s' "$stale" | tr '\n' ' ')" "request a confirmation or a new round"; fi
  fi
}

check_no_open() { # $1 review file
  if grep -E -q '^\| *[0-9]+ *\|.*\| *open *\| *$' "$1" 2>/dev/null; then
    fail "review.md has findings with Status open" "fix them (or wont-fix with reason) — status is never waivable"
  else ok "no finding left open"; fi
}

check_tasks_done() { # $1 tasks file
  n=$(grep -c '^- \[ \] ' "$1" 2>/dev/null || true)
  if [ "${n:-0}" -eq 0 ]; then ok "tasks.md: every task checked"; else fail "tasks.md: $n unchecked task(s)" "finish or descope them — task completion is never waivable"; fi
}

check_state() { # $1 handoff file, $2 expected state
  st=$(grep -E -m1 '^\*\*State:\*\*' "$1" 2>/dev/null | sed -E 's/^\*\*State:\*\* *//; s/ *$//')
  if [ "$st" = "$2" ]; then ok "handoff.md State is $2"; else fail "handoff.md State is '${st:-missing}', expected $2" "run /workflow:handoff"; fi
}

MODE=${1:-}; ARG=${2:-}; GATE=${3:-}
case "$MODE" in
  decision) [ -n "$ARG" ] && [ -n "$GATE" ] || usage; decision "$ARG" "$GATE"; exit $? ;;
  tier) [ -n "$ARG" ] || usage; t=$(tier "$ARG"); [ -n "$t" ] && { printf '%s\n' "$t"; exit 0; } || exit 1 ;;
  mode) mode; exit 0 ;;
  apply|merge|archive) [ -n "$ARG" ] || usage ;;
  *) usage ;;
esac

ID=$ARG; DIR="openspec/changes/$ID"; BRANCH="change/$ID"; HEAD_BRANCH=$(git rev-parse --abbrev-ref HEAD)

case "$MODE" in
apply)
  [ -d "$DIR" ] || fail "no such change: $DIR" "openspec new change $ID (via /workflow:start)"
  [ "$HEAD_BRANCH" = "$BRANCH" ] && ok "on branch $BRANCH" || fail "on branch $HEAD_BRANCH, not $BRANCH" "git checkout $BRANCH"
  [ -f "$DIR/tasks.md" ] && ok "tasks.md exists" || fail "tasks.md missing" "finish /opsx:propose first"
  T=$(tier "$DIR/proposal.md"); [ -n "$T" ] && ok "risk tier: $T" || fail "proposal.md has no valid Risk-Tier" "declare **Risk-Tier:** low|medium|high"
  if [ "$T" = high ]; then check_gate "$DIR/review.md" 1 "$ID" ""; else note "tier ${T:-?}: Gate 1 not required"; fi
  ;;
merge)
  git rev-parse --verify -q "$BRANCH" >/dev/null || { fail "no such branch: $BRANCH" ""; }
  if git rev-parse --verify -q "$BRANCH" >/dev/null; then
    [ -n "$(git log main.."$BRANCH" --oneline 2>/dev/null)" ] && ok "$BRANCH is ahead of main" || fail "$BRANCH has no commits over main" "nothing to merge"
    git merge-base --is-ancestor main "$BRANCH" 2>/dev/null && ok "$BRANCH contains current main" || fail "$BRANCH is behind main" "merge main into the change branch first"
    TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
    for f in proposal.md tasks.md handoff.md review.md; do git show "$BRANCH:$DIR/$f" > "$TMP/$f" 2>/dev/null || : > "$TMP/$f"; done
    T=$(tier "$TMP/proposal.md"); [ -n "$T" ] && ok "risk tier: $T" || fail "proposal.md has no valid Risk-Tier" "declare **Risk-Tier:** low|medium|high"
    check_tasks_done "$TMP/tasks.md"
    check_state "$TMP/handoff.md" ready-to-merge
    case "$T" in
      high)   check_gate "$TMP/review.md" 1 "$ID" ""; check_gate "$TMP/review.md" 2 "$ID" "$BRANCH"; check_no_open "$TMP/review.md" ;;
      medium) check_gate "$TMP/review.md" 2 "$ID" "$BRANCH"; check_no_open "$TMP/review.md" ;;
      low)    note "tier low: no gate required; make check and CI are the floor" ;;
    esac
    if [ "$HEAD_BRANCH" = "$BRANCH" ]; then
      if command -v openspec >/dev/null 2>&1; then
        openspec validate "$ID" --strict >/dev/null 2>&1 && ok "openspec validate --strict" || fail "openspec validate $ID --strict fails" "fix the artifacts"
      else fail "openspec CLI not installed" "npm install -g @fission-ai/openspec"; fi
    else note "strict validation runs after checkout (/git:merge step 5)"; fi
  fi
  ;;
archive)
  [ "$HEAD_BRANCH" = main ] && ok "on main" || fail "archive runs on main, not $HEAD_BRANCH" "merge first (/git:merge)"
  [ -d "$DIR" ] || fail "no such change on main: $DIR" "was the branch merged?"
  if git rev-parse --verify -q "$BRANCH" >/dev/null; then
    git merge-base --is-ancestor "$BRANCH" main && ok "$BRANCH is merged into main" || fail "$BRANCH is not merged into main" "/git:merge $ID"
  else note "branch $BRANCH already deleted; trusting the change directory on main"; fi
  T=$(tier "$DIR/proposal.md"); [ -n "$T" ] && ok "risk tier: $T" || fail "proposal.md has no valid Risk-Tier" ""
  check_tasks_done "$DIR/tasks.md"
  check_state "$DIR/handoff.md" merged
  case "$T" in
    high)   check_gate "$DIR/review.md" 1 "$ID" ""; check_gate "$DIR/review.md" 2 "$ID" ""; check_no_open "$DIR/review.md" ;;
    medium) check_gate "$DIR/review.md" 2 "$ID" ""; check_no_open "$DIR/review.md" ;;
  esac
  ;;
esac

if [ "$FAILURES" -eq 0 ]; then printf 'workflow-verify: %s %s — all checks passed\n' "$MODE" "$ID"; exit 0
else printf 'workflow-verify: %s %s — %d check(s) FAILED\n' "$MODE" "$ID" "$FAILURES"; exit 1; fi
