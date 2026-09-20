#!/bin/sh
# The gate runner — ONE process performs the mechanical floor and the
# reviewer step, so "the runner is the only path to the reviewer" holds
# by construction. Lean adaptation of narrative-forge ADR-097 (no
# telemetry, no record grammar beyond kind/gate/commit binding).
#
# Two review modes, declared in AGENTS.md as `**Review mode:** auto|manual`
# (absent = auto):
#   auto    the runner invokes Codex headlessly, verifies and commits
#   manual  the executor REQUESTS a review (floor + printed prompt), the
#           user runs Codex by hand, then the executor RECORDS the result
#           (same verification and commit as auto)
#
# Usage:
#   gate-run.sh <change-id> <1|2> full                     auto: full round
#   gate-run.sh <change-id> <1|2> confirm <source-round>   auto: scoped confirmation
#   gate-run.sh <change-id> <1|2> request [<source-round>] manual: floor, then print the
#                                                          prompt for the user (round given
#                                                          = confirmation request)
#   gate-run.sh <change-id> <1|2> record                   manual: verify the record Codex
#                                                          left in review.md, commit it
#
# Exit (fail-closed):
#   0  the record verified and review.md committed (full/confirm/record),
#      or the request was printed (request)
#   1  a precondition failed, or the record did not verify — review.md
#      is then left MODIFIED for inspection; nothing is committed
#   2  usage error
#   3  another run holds the lock
set -u
say() { printf 'gate-run: %s\n' "$1"; }
die() { printf 'gate-run: %s\n' "$1" >&2; exit "$2"; }

# 1. arguments (reads no repository state)
ID=${1:-}; GATE=${2:-}; OP=${3:-}; ROUND=${4:-}
[ -n "$ID" ] && [ -n "$GATE" ] && [ -n "$OP" ] || die "usage: $0 <change-id> <1|2> full | confirm <round> | request [<round>] | record" 2
case "$GATE" in 1|2) ;; *) die "gate must be 1 or 2, got '$GATE'" 2 ;; esac
case "$OP" in
  full|record) [ -z "$ROUND" ] || die "$OP takes no source round" 2 ;;
  confirm) case "$ROUND" in ''|*[!0-9]*) die "confirm requires a numeric source round" 2 ;; esac ;;
  request) case "$ROUND" in '') ;; *[!0-9]*) die "request takes an optional numeric source round" 2 ;; esac ;;
  *)       die "operation must be full, confirm, request or record, got '$OP'" 2 ;;
esac
[ "$#" -le 4 ] || die "unexpected extra arguments: nothing but the named placeholders reaches the prompt" 2

# 2. the lock, before any repository read; refuse rather than queue
ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || die "not inside a git repository" 1
LOCK="${TMPDIR:-/tmp}/gate-run.$(printf '%s' "$ROOT" | cksum | cut -d' ' -f1).lock"
mkdir "$LOCK" 2>/dev/null || die "another gate run holds the lock: $(cat "$LOCK/owner" 2>/dev/null || echo unknown) (remove $LOCK only if that run is dead)" 3
ERRLOG=$(mktemp) || die "cannot create a log file" 1
trap 'rm -rf "$LOCK"; rm -f "$ERRLOG" "$ERRLOG.rec"' EXIT
trap 'exit 1' INT TERM
printf '%s gate%s %s pid=%s\n' "$ID" "$GATE" "$OP" "$$" > "$LOCK/owner"
cd "$ROOT" || die "cannot enter $ROOT" 1

# 3. review mode and operation compatibility
MODE=auto
if [ -f AGENTS.md ]; then
  m=$(grep -E -m1 '^\*\*Review mode:\*\* *(auto|manual) *$' AGENTS.md | sed -E 's/^\*\*Review mode:\*\* *//; s/ *$//')
  [ -z "$m" ] || MODE=$m
fi
case "$MODE:$OP" in
  auto:full|auto:confirm) command -v codex >/dev/null 2>&1 || die "codex CLI not installed (npm install -g @openai/codex)" 1 ;;
  auto:request|auto:record) die "review mode is auto (AGENTS.md): use 'full' or 'confirm <round>' — the runner invokes Codex itself" 1 ;;
  manual:full|manual:confirm) die "review mode is manual (AGENTS.md): use 'request [<round>]', let the user run Codex, then 'record'" 1 ;;
esac

# 4. repository validation
DIR="openspec/changes/$ID"; REVIEW="$DIR/review.md"; BRANCH="change/$ID"
[ -d "$DIR" ] || die "no such change: $DIR" 1
git rev-parse --verify -q "$BRANCH" >/dev/null || die "no such branch: $BRANCH" 1
[ "$(git rev-parse --abbrev-ref HEAD)" = "$BRANCH" ] || die "checkout $BRANCH before running the gate" 1
if [ "$OP" = record ]; then
  dirty=$(git status --porcelain)
  [ -n "$dirty" ] || die "nothing to record: $REVIEW is unchanged — did the reviewer write its record?" 1
  [ "$(printf '%s\n' "$dirty" | wc -l)" -eq 1 ] && [ "${dirty##* }" = "$REVIEW" ] || die "the working tree has changes other than $REVIEW: $(printf '%s' "$dirty" | tr '\n' ' ') — the reviewer may modify only review.md" 1
else
  [ -z "$(git status --porcelain)" ] || die "working tree is dirty; commit or stash first" 1
fi
[ "$GATE" = 2 ] && [ -z "$(git log main.."$BRANCH" --oneline)" ] && die "gate 2 needs implementation commits on $BRANCH" 1
SHA=$(git rev-parse HEAD)

# helpers over review.md
round_commit() { # $1 round → Reviewed-Commit of "## Round $1 · Gate $GATE", empty if absent
  awk -v r="$1" -v g="$GATE" '
    /^## /{ in_r = ($0 ~ ("^## Round " r " · Gate " g " *$")) }
    in_r && /^\*\*Reviewed-Commit:\*\*/ { print $NF; exit }' "$REVIEW"
}
round_open_rows() { # $1 round → finding rows still open in that round
  awk -v r="$1" -v g="$GATE" '/^## /{ in_r = ($0 ~ ("^## Round " r " · Gate " g " *$")) } in_r && /^\| *[0-9]+ *\|/ && /\| *open *\| *$/' "$REVIEW"
}
confirm_preconditions() { # $1 source round; sets BASE
  [ -f "$REVIEW" ] || die "no review.md to confirm against" 1
  BASE=$(round_commit "$1")
  [ -n "$BASE" ] || die "round $1 at gate $GATE not found in $REVIEW" 1
  [ -z "$(round_open_rows "$1")" ] || die "round $1 still has findings with Status open — set each to fixed or wont-fix (+reason) before requesting a confirmation" 1
}

# 5. manual mode: RECORD what the reviewer left (no floor — the commit is the one requested)
if [ "$OP" = record ]; then
  last_heading=$(grep -n '^## ' "$REVIEW" | tail -1); last_line=${last_heading%%:*}; last_text=${last_heading#*:}
  if printf '%s\n' "$last_text" | grep -E -q "^## Round [0-9]+ · Gate $GATE *\$"; then KIND=Round; OPNAME=full
  elif printf '%s\n' "$last_text" | grep -E -q "^## Confirmation [0-9]+ · Gate $GATE · Round [0-9]+ *\$"; then
    KIND=Confirmation; OPNAME=confirm
    src=$(printf '%s' "$last_text" | sed -E 's/.*· Round ([0-9]+) *$/\1/')
    [ -n "$(round_commit "$src")" ] || die "confirmation names round $src, which does not exist at gate $GATE" 1
    [ -z "$(round_open_rows "$src")" ] || die "round $src still has findings with Status open — a confirmation cannot close them" 1
  else die "last record is '${last_text:-none}', expected a Round or Confirmation for gate $GATE" 1; fi
  tail -n +"$last_line" "$REVIEW" > "$ERRLOG.rec"
  grep -E -q "^\*\*Reviewed-Commit:\*\* *$SHA *\$" "$ERRLOG.rec" || die "record is not bound to the current commit $SHA (was something committed after the request?)" 1
  verdict=$(grep -E -m1 '^\*\*Verdict:\*\*' "$ERRLOG.rec" | sed -E 's/^\*\*Verdict:\*\* *//; s/ *$//')
  case "$KIND:$verdict" in
    Round:approved|Round:changes-requested|Confirmation:confirmed|Confirmation:changes-requested) ;;
    *) die "record verdict '${verdict:-missing}' is not valid for a $KIND" 1 ;;
  esac
  git add "$REVIEW" || die "cannot stage $REVIEW" 1
  git commit -q -m "review: gate $GATE $OPNAME — $verdict ($ID)" -m "Reviewed-Commit: $SHA" -m "Co-Authored-By: Codex <noreply@openai.com>" || die "cannot commit $REVIEW" 1
  say "$KIND recorded: $verdict"
  say "committed $(git rev-parse --short HEAD)"
  exit 0
fi

# 6. the mechanical floor (full, confirm, request)
say "mechanical floor"
scripts/pregate-verify.sh "gate$GATE" "$ID" || die "mechanical floor FAILED — the reviewer was not invoked" 1

# 7. prompt bindings (constants; identifiers only)
if [ "$OP" = confirm ] || { [ "$OP" = request ] && [ -n "$ROUND" ]; }; then
  confirm_preconditions "$ROUND"
  WANT="^## Confirmation [0-9]+ · Gate $GATE · Round $ROUND *\$"; KIND=Confirmation
  PROMPT=$(printf 'Confirm resolution of every blocker and major finding of round %s at Gate %s of OpenSpec change %s on branch change/%s, per the review protocol in AGENTS.md. Review only the diff from %s to %s and collateral effects reachable from the named findings. Do not introduce unrelated minor findings. Return confirmed or changes-requested per finding as a new "## Confirmation <n> · Gate %s · Round %s" block in openspec/changes/%s/review.md, with the Reviewed-Commit line set to %s. Modify no other file and run no git write commands.' \
    "$ROUND" "$GATE" "$ID" "$ID" "$BASE" "$SHA" "$GATE" "$ROUND" "$ID" "$SHA")
else
  WANT="^## Round [0-9]+ · Gate $GATE *\$"; KIND=Round
  PROMPT=$(printf 'Perform Gate %s review of OpenSpec change %s on branch change/%s per the review protocol in AGENTS.md. Reviewed commit: %s. Write your verdict as a new "## Round <n> · Gate %s" block in openspec/changes/%s/review.md, including the Reviewed-Commit line set to %s. Modify no other file and run no git write commands.' \
    "$GATE" "$ID" "$ID" "$SHA" "$GATE" "$ID" "$SHA")
fi

# 8. manual mode: REQUEST — print the prompt, change nothing, stop
if [ "$OP" = request ]; then
  what=full; [ -z "$ROUND" ] || what="confirm round $ROUND"
  say "review requested: gate $GATE, $what, commit $SHA — floor passed, nothing committed"
  say "hand this prompt to Codex yourself (interactive 'codex' in $ROOT, or the one-liner), commit NOTHING meanwhile,"
  say "then run: scripts/gate-run.sh $ID $GATE record"
  printf -- '--- prompt ---\n%s\n--- one-liner ---\ncodex exec -C "%s" -s workspace-write --ignore-user-config '"'"'%s'"'"'\n' "$PROMPT" "$ROOT" "$PROMPT"
  exit 0
fi

# 9. auto mode: the bounded hermetic invocation
say "invoking the reviewer ($OP, gate $GATE, commit $SHA)"
START=$(date +%s)
timeout 1800 codex exec -C "$ROOT" -s workspace-write --ignore-user-config "$PROMPT" </dev/null >/dev/null 2>"$ERRLOG"
RC=$?
ELAPSED=$(( $(date +%s) - START ))
[ "$RC" -ne 124 ] || die "the reviewer timed out after 1800s — the gate is NOT passed" 1
[ "$RC" -eq 0 ] || { tail -n 3 "$ERRLOG" >&2; die "the reviewer exited $RC — the gate is NOT passed" 1; }

# 10. verification of the reviewer's output
dirty=$(git status --porcelain)
[ "$(printf '%s\n' "$dirty" | wc -l)" -eq 1 ] && [ "${dirty##* }" = "$REVIEW" ] || die "the reviewer modified something other than $REVIEW: ${dirty:-nothing}" 1
last_heading=$(grep -n '^## ' "$REVIEW" | tail -1); last_line=${last_heading%%:*}; last_text=${last_heading#*:}
printf '%s\n' "$last_text" | grep -E -q "$WANT" || die "last record is '$last_text', expected a $KIND for gate $GATE" 1
tail -n +"$last_line" "$REVIEW" > "$ERRLOG.rec"
grep -E -q "^\*\*Reviewed-Commit:\*\* *$SHA *\$" "$ERRLOG.rec" || die "record is not bound to the reviewed commit $SHA" 1
verdict=$(grep -E -m1 '^\*\*Verdict:\*\*' "$ERRLOG.rec" | sed -E 's/^\*\*Verdict:\*\* *//; s/ *$//')
case "$KIND:$verdict" in
  Round:approved|Round:changes-requested|Confirmation:confirmed|Confirmation:changes-requested) ;;
  *) die "record verdict '${verdict:-missing}' is not valid for a $KIND" 1 ;;
esac

# 11. the commit
git add "$REVIEW" || die "cannot stage $REVIEW" 1
git commit -q -m "review: gate $GATE $OP — $verdict ($ID)" -m "Reviewed-Commit: $SHA" -m "Co-Authored-By: Codex <noreply@openai.com>" || die "cannot commit $REVIEW" 1
say "$KIND recorded: $verdict (${ELAPSED}s)"
say "committed $(git rev-parse --short HEAD)"
exit 0
