#!/bin/sh
# Fixture suite for scripts/gate-run.sh and scripts/pregate-verify.sh:
# a throwaway repository, a stubbed `codex` and `openspec` on PATH, one
# demonstrated failing input per rule. Never invokes the real reviewer.
# Usage: scripts/gate_run_test.sh ; exit non-zero on any failing case.
set -u
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
G="$HERE/gate-run.sh"; PG="$HERE/pregate-verify.sh"; WV="$HERE/workflow-verify.sh"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
export TMPDIR="$TMP"            # the runner's lock lives under TMPDIR
PASS=0; FAILED=0
texit() { exp=$1; shift; "$@" >"$TMP/out" 2>&1; rc=$?; if [ "$rc" -eq "$exp" ]; then PASS=$((PASS+1)); else FAILED=$((FAILED+1)); printf 'FAIL (exit %s, expected %s): %s\n' "$rc" "$exp" "$*"; sed 's/^/    /' "$TMP/out" | tail -5; fi; }
tgrep(){ pat=$1; shift; if "$@" 2>&1 | grep -q -- "$pat"; then PASS=$((PASS+1)); else FAILED=$((FAILED+1)); printf 'FAIL (no match %s): %s\n' "$pat" "$*"; fi; }
tfile(){ if [ -e "$1" ]; then PASS=$((PASS+1)); else FAILED=$((FAILED+1)); printf 'FAIL: expected file %s\n' "$1"; fi; }
tempty(){ if [ -z "$("$@" 2>/dev/null)" ]; then PASS=$((PASS+1)); else FAILED=$((FAILED+1)); printf 'FAIL (expected empty output): %s\n' "$*"; fi; }
tnofile(){ if [ ! -e "$1" ]; then PASS=$((PASS+1)); else FAILED=$((FAILED+1)); printf 'FAIL: unexpected file %s\n' "$1"; fi; }

# --- stubs ------------------------------------------------------------
mkdir -p "$TMP/bin"; export STUB="$TMP/stub"; mkdir -p "$STUB"
printf '#!/bin/sh\nexit 0\n' > "$TMP/bin/openspec"; chmod +x "$TMP/bin/openspec"
cat > "$TMP/bin/codex" <<'STUB'
#!/bin/sh
# codex stub: honours -C <root>, takes the LAST argument as the prompt,
# behaves per $STUB/mode: ok | cr | wrongsha | extra | fail
set -u
ROOT=.; prev=""; for a; do [ "$prev" = "-C" ] && ROOT=$a; prev=$a; done; PROMPT=$prev
printf '%s\n' "$PROMPT" > "$STUB/invoked"
mode=$(cat "$STUB/mode" 2>/dev/null || echo ok)
[ "$mode" = fail ] && exit 1
ID=$(printf '%s' "$PROMPT" | sed -n 's/.*OpenSpec change \([^ ]*\) on branch.*/\1/p')
GATE=$(printf '%s' "$PROMPT" | sed -n 's/.*Gate \([12]\) .*/\1/p' | head -1)
R="$ROOT/openspec/changes/$ID/review.md"
case "$PROMPT" in
  Confirm*) SHA=$(printf '%s' "$PROMPT" | sed -n 's/.*line set to \([0-9a-f]*\).*/\1/p'); RND=$(printf '%s' "$PROMPT" | sed -n 's/.*of round \([0-9]*\) at Gate.*/\1/p'); KIND=conf ;;
  *)        SHA=$(printf '%s' "$PROMPT" | sed -n 's/.*Reviewed commit: \([0-9a-f]*\)\..*/\1/p'); KIND=round ;;
esac
[ "$mode" = wrongsha ] && SHA=0000000000000000000000000000000000000000
[ -f "$R" ] || printf '# Review — %s\n' "$ID" > "$R"
if [ "$KIND" = round ]; then
  n=$(( $(grep -c "^## Round [0-9]* · Gate $GATE" "$R") + 1 ))
  v=approved; [ "$mode" = cr ] && v=changes-requested
  printf '\n## Round %s · Gate %s\n**Reviewer:** codex\n**Date:** 2026-01-01\n**Reviewed-Commit:** %s\n**Verdict:** %s\n\n### Findings\n| # | Severity | Location | Finding | Status |\n|---|---|---|---|---|\n' "$n" "$GATE" "$SHA" "$v" >> "$R"
  [ "$v" = changes-requested ] && printf '| 1 | major | tasks.md | vague | open |\n' >> "$R"
else
  n=$(( $(grep -c "^## Confirmation [0-9]* · Gate $GATE" "$R") + 1 ))
  printf '\n## Confirmation %s · Gate %s · Round %s\n**Reviewer:** codex\n**Date:** 2026-01-01\n**Reviewed-Commit:** %s\n**Verdict:** confirmed\n\n### Findings\n| # | Resolution |\n|---|---|\n| 1 | confirmed |\n' "$n" "$GATE" "$RND" "$SHA" >> "$R"
fi
[ "$mode" = extra ] && echo x > "$ROOT/extra.txt"
exit 0
STUB
chmod +x "$TMP/bin/codex"; PATH="$TMP/bin:$PATH"; echo ok > "$STUB/mode"

# --- repository -------------------------------------------------------
R="$TMP/repo"; mkdir -p "$R"; cd "$R"
git init -q -b main .; git config user.email t@t; git config user.name t
printf 'check:\n\t@true\n' > Makefile
mkdir scripts; cp "$HERE"/*.sh scripts/; chmod +x scripts/*.sh   # the runner calls scripts/ relative to the repo root
git add -A; git commit -q -m init
git checkout -q -b change/c; mkdir -p openspec/changes/c
printf '# c\n\n**Risk-Tier:** medium\n\n## Why\n\n## Non-goals\n- none\n' > openspec/changes/c/proposal.md
printf '# Tasks\n- [x] 1.1 wrote `Makefile`\n' > openspec/changes/c/tasks.md
printf '# Handoff\n\n**State:** awaiting-gate-2\n' > openspec/changes/c/handoff.md
git add -A; git commit -q -m "feat(c): work"

# --- pregate-verify ---------------------------------------------------
texit 0 "$PG" gate2 c
texit 2 "$PG" gate3 c                                    # usage
texit 1 "$PG" gate2 nosuch
sed -i '/Non-goals/d' openspec/changes/c/proposal.md; git commit -q -am "drop non-goals"
texit 1 "$PG" gate2 c; git reset -q --hard HEAD~1         # non-goals required
printf -- '- [ ] 1.2 later\n' >> openspec/changes/c/tasks.md; git commit -q -am "open task"
texit 1 "$PG" gate2 c                                    # unchecked task blocks gate 2
texit 0 "$PG" gate1 c; git reset -q --hard HEAD~1         # …but not gate 1
printf -- '- [x] 1.3 wrote `docs/missing.md`\n' >> openspec/changes/c/tasks.md; git commit -q -am "phantom output"
texit 1 "$PG" gate2 c; git reset -q --hard HEAD~1         # checked task names a missing file
sed -i 's/medium/high/' openspec/changes/c/proposal.md; git commit -q -am "tier high"
texit 1 "$PG" gate1 c                                    # high tier needs an applicability table
printf '# Design\n\n## Applicability\n| q | a |\n' > openspec/changes/c/design.md; git add -A; git commit -q -m "design"
texit 0 "$PG" gate1 c; git reset -q --hard HEAD~2
printf 'nothing:\n\t@true\n' > Makefile; git commit -q -am "no check target"
texit 1 "$PG" gate2 c; git reset -q --hard HEAD~1         # make check must exist at gate 2
printf 'check:\n\t@exit 1\n' > Makefile; git commit -q -am "red check"
texit 1 "$PG" gate2 c; git reset -q --hard HEAD~1         # …and be green
printf '# whitespace \n' > ws.md; git add ws.md; git commit -q -m "ws"
texit 1 "$PG" gate2 c; git reset -q --hard HEAD~1         # git diff --check

# --- gate-run: arguments and preconditions ----------------------------
texit 2 "$G"
texit 2 "$G" c 3 full
texit 2 "$G" c 2 confirm
texit 2 "$G" c 2 full extra
texit 2 "$G" c 2 bogus
git checkout -q main; texit 1 "$G" c 2 full; git checkout -q change/c     # wrong branch
echo dirty > dirty.txt; texit 1 "$G" c 2 full; rm dirty.txt              # dirty tree
LOCK="$TMP/gate-run.$(printf '%s' "$R" | cksum | cut -d' ' -f1).lock"
mkdir "$LOCK"; echo "someone" > "$LOCK/owner"; texit 3 "$G" c 2 full; rmdir_out=$(rm -rf "$LOCK")
tnofile "$LOCK"                                                            # (removed by us; the runner must not have touched it)
rm -f "$STUB/invoked"
sed -i '/Risk-Tier/d' openspec/changes/c/proposal.md; git commit -q -am "no tier"
texit 1 "$G" c 2 full; tnofile "$STUB/invoked"                             # floor fails → reviewer never invoked
git reset -q --hard HEAD~1
tnofile "$LOCK"                                                            # lock released on failure

# --- gate-run: the reviewer's output ---------------------------------
echo wrongsha > "$STUB/mode"; texit 1 "$G" c 2 full
tgrep 'openspec/changes/c/review.md' git status --porcelain               # left in the tree for inspection (new file → ??)
git checkout -q -- .; git clean -qfd
echo extra > "$STUB/mode"; texit 1 "$G" c 2 full; git checkout -q -- .; git clean -qfd
echo fail > "$STUB/mode"; texit 1 "$G" c 2 full
tempty git status --porcelain                                          # nothing left behind
echo ok > "$STUB/mode"

# --- gate-run: happy paths -------------------------------------------
HEAD0=$(git rev-parse HEAD)
texit 0 "$G" c 2 full
tgrep "^review: gate 2 full — approved (c)" git log -1 --format=%s
tgrep "Co-Authored-By: Codex" git log -1 --format=%b
tgrep "^Round approved $HEAD0" "$WV" decision openspec/changes/c/review.md 2
tempty git status --porcelain
tnofile "$LOCK"
tgrep "Reviewed commit: $HEAD0" cat "$STUB/invoked"                        # prompt carries identifiers only

# gate 1 changes-requested, then confirm
echo cr > "$STUB/mode"; texit 0 "$G" c 1 full
tgrep "^Round changes-requested" "$WV" decision openspec/changes/c/review.md 1
echo ok > "$STUB/mode"
texit 1 "$G" c 1 confirm 1                                                 # finding #1 still open → refused
texit 1 "$G" c 1 confirm 7                                                 # no such round
printf -- '- [x] 1.2 clarified\n' >> openspec/changes/c/tasks.md
sed -i 's/| vague | open |/| vague | fixed |/' openspec/changes/c/review.md      # Status dispositioned by the executor
git commit -q -am "fix(c): clarify (gate 1 #1)"
H=$(git rev-parse HEAD)
texit 0 "$G" c 1 confirm 1
tgrep "^Confirmation confirmed $H" "$WV" decision openspec/changes/c/review.md 1
tgrep "review: gate 1 confirm — confirmed (c)" git log -1 --format=%s

# --- manual review mode ----------------------------------------------
printf '# Rules\n\n**Review mode:** manual\n' > AGENTS.md; git add AGENTS.md; git commit -q -m "manual mode"
rm -f "$STUB/invoked"
texit 1 "$G" c 2 full; tnofile "$STUB/invoked"                             # auto ops refused in manual mode
texit 1 "$G" c 2 confirm 1
texit 2 "$G" c 2 request x                                                 # round must be numeric
texit 2 "$G" c 2 record 1                                                  # record takes no round
HEADM=$(git rev-parse HEAD)
texit 0 "$G" c 2 request; tnofile "$STUB/invoked"                          # request: floor passed, codex never invoked
tgrep "Reviewed commit: $HEADM" "$G" c 2 request                           # the printed prompt is bound to HEAD
tgrep "gate-run.sh c 2 record" "$G" c 2 request                            # …and names the follow-up
tempty git status --porcelain                                              # nothing written, nothing committed
[ "$(git rev-parse HEAD)" = "$HEADM" ] && PASS=$((PASS+1)) || { FAILED=$((FAILED+1)); echo "FAIL: request must not commit"; }
sed -i '/Non-goals/d' openspec/changes/c/proposal.md; git commit -q -am "drop non-goals"
texit 1 "$G" c 2 request; git reset -q --hard HEAD~1                       # request obeys the floor
texit 1 "$G" c 2 record                                                    # nothing to record
# (round 1 at gate 2 exists from the auto section above)
# the user's reviewer writes a record bound to the wrong commit
printf '\n## Round 2 · Gate 2\n**Reviewer:** codex\n**Date:** 2026-01-01\n**Reviewed-Commit:** 0000000000000000000000000000000000000000\n**Verdict:** approved\n' >> openspec/changes/c/review.md
texit 1 "$G" c 2 record; tgrep 'review.md' git status --porcelain          # left modified for inspection
git checkout -q -- .; git clean -qfd                                       # review.md is still untracked here
# a valid record plus a stray file
printf '\n## Round 2 · Gate 2\n**Reviewer:** codex\n**Date:** 2026-01-01\n**Reviewed-Commit:** %s\n**Verdict:** approved\n' "$HEADM" >> openspec/changes/c/review.md
echo x > extra.txt; texit 1 "$G" c 2 record; rm -f extra.txt
# a Round with a Confirmation verdict
sed -i 's/\*\*Verdict:\*\* approved$/**Verdict:** confirmed/' openspec/changes/c/review.md
texit 1 "$G" c 2 record; git checkout -q -- .; git clean -qfd
# happy path: changes-requested round, dispositioned, confirmation requested and recorded
printf '\n## Round 2 · Gate 2\n**Reviewer:** codex\n**Date:** 2026-01-01\n**Reviewed-Commit:** %s\n**Verdict:** changes-requested\n\n### Findings\n| # | Severity | Location | Finding | Status |\n|---|---|---|---|---|\n| 1 | major | tasks.md | vague | open |\n' "$HEADM" >> openspec/changes/c/review.md
texit 0 "$G" c 2 record
tgrep "^review: gate 2 full — changes-requested (c)" git log -1 --format=%s
tgrep "Co-Authored-By: Codex" git log -1 --format=%b
tgrep "^Round changes-requested $HEADM" "$WV" decision openspec/changes/c/review.md 2
tempty git status --porcelain
texit 1 "$G" c 2 request 2                                                 # finding #1 still open → refused
texit 1 "$G" c 2 request 7                                                 # no such round
sed -i 's/| vague | open |/| vague | fixed |/' openspec/changes/c/review.md; git commit -q -am "fix(c): clarify (gate 2 #1)"
HEADC=$(git rev-parse HEAD)
tgrep "Confirm resolution of every blocker and major finding of round 2 at Gate 2" "$G" c 2 request 2
tgrep "from $HEADM to $HEADC" "$G" c 2 request 2                            # confirmation diff bounds
printf '\n## Confirmation 1 · Gate 2 · Round 2\n**Reviewer:** codex\n**Date:** 2026-01-01\n**Reviewed-Commit:** %s\n**Verdict:** confirmed\n\n### Findings\n| # | Resolution |\n|---|---|\n| 1 | confirmed |\n' "$HEADC" >> openspec/changes/c/review.md
texit 0 "$G" c 2 record
tgrep "^review: gate 2 confirm — confirmed (c)" git log -1 --format=%s
tgrep "^Confirmation confirmed $HEADC" "$WV" decision openspec/changes/c/review.md 2
# a confirmation naming a round that does not exist
printf '\n## Confirmation 2 · Gate 2 · Round 9\n**Reviewed-Commit:** %s\n**Verdict:** confirmed\n' "$HEADC" >> openspec/changes/c/review.md
texit 1 "$G" c 2 record; git checkout -q -- .
tnofile "$LOCK"
# back to auto: manual ops refused
git rm -q AGENTS.md; git commit -q -m "auto mode"
texit 1 "$G" c 2 request
texit 1 "$G" c 2 record

# gate 2 with no commits over main
git checkout -q main; mkdir -p openspec/changes/e
printf '# e\n\n**Risk-Tier:** low\n\n## Non-goals\n- none\n' > openspec/changes/e/proposal.md
printf -- '- [x] 1.1 wrote `Makefile`\n' > openspec/changes/e/tasks.md
git add -A; git commit -q -m "chore: e on main"; git checkout -q -b change/e
texit 1 "$G" e 2 full
git checkout -q change/c

printf 'gate_run_test: %d passed, %d failed\n' "$PASS" "$FAILED"
[ "$FAILED" -eq 0 ]
