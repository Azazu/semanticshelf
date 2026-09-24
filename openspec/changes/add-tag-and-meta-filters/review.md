# Review — add-tag-and-meta-filters

## Round 1 · Gate 1
**Reviewer:** codex
**Date:** 2026-09-23
**Reviewed-Commit:** d760236ca902bfd8cb8d48d5a8155b5844f04c27
**Verdict:** changes-requested

### Findings
| # | Severity | Location | Finding | Status |
|---|----------|----------|---------|--------|
| 1 | major | design.md decision 3; tasks.md 3.1, 3.4; specs/text-search/spec.md pagination | The exhaustion probe is explicitly skipped for every full page, but a full page does not prove that the lookahead was obtained. With `limit=20`, suppose the bounded scan finds exactly 20 matching rows while at least 21 exist. The existing `limit + 1` mechanism returns `has_more=false`, and this design skips the probe and the warning because the page is full. It therefore still presents a budget-limited answer as the end of the ranking. Base the decision on whether the pre-threshold scan supplied the required lookahead, accounting for offset and self-exclusion, rather than whether the rendered page is full. Specify the envelope's behavior and add a regression for exactly `limit` matches reached with additional matches outside the scan budget; preserve the no-probe fast path when the lookahead is actually present. | fixed |
| 2 | major | design.md decision 3; tasks.md 3.1–3.3 | Comparing the short answer with the number of assets satisfying only the narrowing cannot establish that the scan stopped early. `nearest_statement` applies `min_score` outside the page, and `_page_of` receives only those surviving rows. For example, ten tagged assets all below the threshold produce an empty answer after a completely exhausted scan; the proposed existence query finds ten matches and falsely reports a scan limit. A nonzero offset likewise requires comparison with the consumed prefix, and a similar-search probe must exclude the query asset and use the selected model. Define the probe inputs and comparison explicitly, retaining pre-threshold scan information so intentional threshold removal is not diagnosed as scan exhaustion. Add tests for threshold-only shortening (including zero surviving hits), an exhausted nonzero-offset page, and self-exclusion, alongside the genuine budget-limited case. | fixed |
| 3 | major | proposal.md Risk-Tier; design.md; tasks.md introduction and validation tasks | The declared medium tier conflicts with AGENTS.md's Security-Sensitive Code rule: any change touching input handling is high tier. Decisions 4–5 introduce a shared validator and raw query/form parsing on four public surfaces, including multipart image search. Binding SQL values is appropriate but does not exempt this work from that rule. Raise the tier to high consistently, add the required applicability table (including empty/zero/null input handling and the applicable boundary questions), and plan demonstrated failing inputs for every new or changed check plus the required security-sensitive commit/handoff flags. A voluntary Gate 1 alone does not satisfy the other high-tier obligations. | fixed |
| 4 | minor | tasks.md 6.1 | `uv run python scripts/…` is a placeholder rather than the exact runnable command required by openspec/config.yaml. Choose the measurement script path and its corpus-size, selectivity, and seed arguments in the plan so the verification and published reproduction command refer to the same concrete invocation. | fixed |

### Validation

Confirmed the current branch is `change/add-tag-and-meta-filters`, HEAD matches
the reviewed commit, and the working tree was clean before this review. Read
AGENTS.md, openspec/config.yaml, every change artifact, the existing text-search
specification, and the current search repository, service, schema and routers.
`scripts/pregate-verify.sh gate1 add-tag-and-meta-filters` passed, including
strict OpenSpec validation. The findings above concern the planned contract
and its verification; implementation and database experiments were not run.

## Confirmation 1 · Gate 1 · Round 1
**Reviewer:** codex
**Date:** 2026-09-23
**Reviewed-Commit:** ffba0ed8e06748a90d76d8d9bf863fed52517583
**Verdict:** changes-requested

### Findings
| # | Resolution |
|---|------------|
| 1 | changes-requested — The exactly-`limit` case and its regression are now covered, but design decision 3 and task 3.2 require `limit + 2` post-exclusion page candidates for `/similar`. The extra self-exclusion slot belongs to the inner window, not to the usable page's lookahead: the existing repository excludes self before OFFSET and caps the page at the requested limit. With public `limit=20`, 21 usable pre-threshold neighbours already supply the lookahead. Requiring 22 either always probes under the retained page shape or, if the page request is enlarged, falsely reports a limit when 21 neighbours were obtained and further neighbours exist. Define window reach separately from the required `limit + 1` usable page rows, and add a `/similar` regression proving no probe runs when that lookahead is present, both when self satisfies the narrowing and when it does not. |
| 2 | changes-requested — Moving threshold removal into the service and binding the probe to model, narrowing and self-exclusion address those parts. However, decision 3 and tasks 3.2–3.3 still equate `offset + candidates` with the consumed prefix without retaining the actual pre-OFFSET count. If `offset=50`, the bounded scan finds 10 of 40 matching neighbours and then stops, the page count is zero and the probe returns 40; `40 > 50 + 0` is false, so the design declares the ranking genuinely exhausted despite the scan stopping early. An empty post-OFFSET page cannot establish that 50 rows were consumed. Preserve the actual count reached after self-exclusion but before OFFSET, including when the page is empty, and compare the bounded probe against that count. Add paired regressions for budget exhaustion before OFFSET and genuine exhaustion before OFFSET, alongside the existing threshold and nonzero-offset cases. |
| 3 | confirmed — Proposal and tasks consistently declare high tier and require both gates, demonstrated failing inputs for every new or changed check, and security-sensitive commit/handoff flags. The design adds the applicability table, including empty input and boundary handling, and the handoff carries the security-sensitive declaration. This confirms the Gate 1 plan; implementation evidence remains a Gate 2 obligation. |

### Validation

Reviewed only the specified commit diff and the existing repository/service
pagination mechanics needed to assess findings 1–3. The branch and HEAD match
the request, and the working tree was clean before review. All source-round
findings had been dispositioned. `scripts/pregate-verify.sh gate1
add-tag-and-meta-filters` passed, including strict OpenSpec validation. The
counterexamples above follow the proposed decision formulas and the current
window/page boundaries; no implementation or database experiments were run.

## Confirmation 2 · Gate 1 · Round 1
**Reviewer:** codex
**Date:** 2026-09-23
**Reviewed-Commit:** e3956bc161624b950ee0024af40d8e0e996eddc1
**Verdict:** confirmed

### Findings
| # | Resolution |
|---|------------|
| 1 | confirmed — Design decision 3 separates window reach (`offset + limit + 1 + excluding`) from usable candidates needed (`offset + limit + 1`). Exactly `limit` matches trigger the bounded probe and the envelope reports an incomplete scan when more exist; a usable lookahead takes the no-probe path. Tasks 3.2–3.3 and 3.5–3.7 cover the full-page case, the report, and `/similar` with exactly `limit + 1` neighbours both when self satisfies the narrowing and when it does not. |
| 2 | confirmed — Candidates and `reached` are retained after self-exclusion but before OFFSET and threshold removal, including when either empties the page. The probe uses the same model and narrowing, excludes self, and compares its count, bounded at `reached + 1`, against actual `reached`. Thus 10 reached at offset 50 with 40 matches reports a cut-short scan, while genuine exhaustion before that offset does not. Tasks 3.1–3.5 cover both cases, threshold-only shortening including zero hits, model isolation and self-exclusion, and preservation of existing page semantics. |
| 3 | confirmed — The high tier, both required gates, applicability table, demonstrated failing inputs for every new or changed check, and security-sensitive commit/handoff declarations remain in the planning artifacts. The resolution confirmed previously is preserved; implementation evidence remains a Gate 2 obligation. |

### Validation

Reviewed the diff from `d760236ca902bfd8cb8d48d5a8155b5844f04c27` to
`e3956bc161624b950ee0024af40d8e0e996eddc1` and collateral pagination behavior
reachable from findings 1–3, including the existing repository/service boundary.
The branch and HEAD match the request, the working tree was clean, and all
source-round findings were dispositioned. Checked the revised formulas against
the prior counterexamples and the planned regressions. The Gate 1 mechanical
floor passed, including strict OpenSpec validation. This confirms the design
and verification plan; no implementation or database experiments were run.

## Round 2 · Gate 1
**Reviewer:** codex
**Date:** 2026-09-23
**Reviewed-Commit:** 0094306c58f7aa0f5a7f210526f1cd5855f265b4
**Verdict:** changes-requested

### Findings
| # | Severity | Location | Finding | Status |
|---|----------|----------|---------|--------|
| 1 | major | specs/text-search/spec.md, requirement "Search is answered from the index, at the depth it is asked for"; design.md Context and decisions 1–2; tasks.md 2.1 | The revised architecture explicitly permits PostgreSQL to answer selective narrowings exactly without the vector index, and its measured table says this happens at selectivities from 1 in 5 to 1 in 100. The delta specification still requires every narrowed search to use that index, with a scenario requiring its scan in the execution plan; task 2.1 retains the same unconditional acceptance criterion. The newly accepted normal execution path therefore violates the proposed normative contract. Revise the delta requirement and verification tasks to permit both plans, distinguishing result correctness from a targeted regression proving the HNSW path remains available and correctly filtered. Preserve the separate unnarrowed-search requirement if intended, and reconcile sibling claims with the revised contract. | fixed |
| 2 | major | tasks.md 3.2, 3.5–3.7; design.md Risks / Trade-offs, scan-bound report | Task 3.5 explicitly removes every database-backed positive scan-limit case and delegates that outcome to unit tests of the arithmetic function. Those tests supply `reached`, `needed` and `matching` themselves; they cannot establish that the service obtains the right counts from a limited scan and its real probe or propagates a true result. The retained integration cases all expect false, while the API field test does not require a real limited scan. Consequently, miswiring the positive service path can pass the planned evidence despite defeating this change's principal guarantee. Add a deterministic positive service/repository regression exercising candidate retrieval, the bounded probe and `scan_limited=true` together, alongside the negative cases. A controlled HNSW-plan fixture with an asserted plan and reduced scan budget is valid coverage of the stale-statistics/index path the design explicitly supports; alternatively define an equally effective controlled boundary test. Demonstrate that disabling the positive-path wiring makes it fail, rather than testing only the Boolean formula. | fixed |
| 3 | major | tasks.md 6.1; design.md decision 7, Applicability and Migration Plan | The runnable benchmark is planned to empty the tables named by ordinary `DATABASE_URL`, explicitly including the development database, and merely print that fact before proceeding. The applicability table nevertheless says every touched path is a read and that nothing deletes, and the plan supplies neither isolation nor an explicit destructive opt-in or a preservation test. Running the published reproduction command can therefore erase an existing corpus and its associated database state. Specify an isolated disposable benchmark database/schema, or an explicit destructive opt-in with a verified target boundary; make the default invocation preserve existing data or refuse before mutation. Cover the benchmark's deletion/crash effects in applicability and add a failing-input test proving an ordinary populated target cannot be emptied by the documented default command. | fixed |

### Validation

Confirmed branch `change/add-tag-and-meta-filters` and HEAD
`0094306c58f7aa0f5a7f210526f1cd5855f265b4`; the working tree was clean before
review. Read AGENTS.md, openspec/config.yaml, the change proposal, design,
tasks, delta specifications, handoff and previous review records. Examined the
revised artifacts since the prior confirmation and the current repository,
service and test boundaries relevant to the revised verification plan.
`scripts/pregate-verify.sh gate1 add-tag-and-meta-filters` passed, including
strict OpenSpec validation. This is a review of the renewed Gate 1 contract and
verification plan, not Gate 2 approval of the partial implementation. No
benchmark, database mutation or implementation test suite was run. Only this
review file was modified; no git write commands were run.

## Confirmation 3 · Gate 1 · Round 2
**Reviewer:** codex
**Date:** 2026-09-23
**Reviewed-Commit:** 7cd7e85bde3fb6518cd379b6c58b4fcd0a490b97
**Verdict:** changes-requested

### Findings
| # | Resolution |
|---|------------|
| 1 | changes-requested — Task 2.1 and the new narrowed-search paragraph permit the exact plan, but the same delta requirement still begins “Every search SHALL be answered from the vector index”, and “The index answers the query” still requires an index scan for an unqualified search. Restrict those retained obligations explicitly to unnarrowed searches. The new assertion that the chosen plan “SHALL NOT change what the answer contains” also conflicts with the supported bounded-index path: task 3.5 deliberately requires a full page without lookahead and `scan_limited=true`, whereas an exact plan with the same remaining matches obtains the lookahead and reports false. State the common filtering, ordering and pagination semantics while explicitly permitting the documented bounded-scan incompleteness and its report; do not require identical answers from the two paths. |
| 2 | confirmed — Task 3.5 now requires an integration regression through real candidate retrieval, the bounded probe and the resulting true flag, asserts the model's vector-index plan, and pairs a reduced-budget full page with a default-budget false result. It explicitly requires failure when the positive-path probe is disabled. Task 3.5a retains the negative cases and tasks 3.6–3.7 retain probe-invocation and envelope coverage. This closes the missing positive-path evidence in the Gate 1 plan; implementation and mutation-test evidence remain Gate 2 obligations. |
| 3 | confirmed — Proposal, design decision 7 and task 6.1 now isolate benchmark writes and deletion in a schema created for the run, with service tables outside that boundary. Applicability covers benchmark deletion and a crash leaving its own schema behind. Task 6.1a requires the default entry point to preserve seeded assets, embeddings and jobs, checks schema cleanup, and specifies the destructive mis-targeting that must make the preservation test fail. This confirms the isolation and verification plan, not an implemented benchmark. |

### Validation

Reviewed only the diff from `0094306c58f7aa0f5a7f210526f1cd5855f265b4`
to `7cd7e85bde3fb6518cd379b6c58b4fcd0a490b97` and collateral contracts
and service count/probe wiring reachable from round 2 findings 1–3.
The requested branch and HEAD match, the working tree was initially clean,
and all source-round findings were dispositioned. The Gate 1 mechanical
floor passed, including strict OpenSpec validation. No benchmark, database
mutation or implementation test suite was run. Only `review.md` was modified;
no git write commands were run.

## Confirmation 4 · Gate 1 · Round 2
**Reviewer:** codex
**Date:** 2026-09-23
**Reviewed-Commit:** 19f60d2048aa94b1fc749cd44a095363baacc6ef
**Verdict:** confirmed

### Findings
| # | Resolution |
|---|------------|
| 1 | confirmed — The delta requirement and its index-plan scenario now explicitly restrict the mandatory vector-index path to unnarrowed searches. Narrowed searches may use either the vector index or exact distances over matching assets. The shared contract specifies filtering, ordering, page bounds, threshold and lookahead semantics while explicitly permitting different completeness and requiring the bounded-scan report. The existing full-page-without-lookahead scenario remains applicable. Task 2.1 permits both plans, and task 3.5 separately verifies the filtered HNSW path. This resolves the normative contradictions identified in confirmation 3. |
| 2 | confirmed — Task 3.5 retains the real-index positive regression through candidate retrieval, the bounded probe and the true flag, with an asserted vector-index plan, a reduced budget yielding a full page without lookahead, and a default-budget false counterpart. Disabling the positive-path probe must make it fail. Tasks 3.5a–3.7 retain negative cases, probe-invocation checks and envelope coverage. The Gate 1 verification obligation is explicit; implemented regression and failing-input evidence remain Gate 2 obligations. |
| 3 | confirmed — Proposal, design decision 7 and task 6.1 keep benchmark mutations inside a schema created for the run, separate from service tables. Applicability covers cleanup deletion and a crash leaving only that schema behind. Task 6.1a requires the default entry point to preserve seeded assets, embeddings and jobs and verifies schema cleanup, with destructive mis-targeting as the demonstrated failing input. The isolation plan remains intact; its implementation and preservation evidence remain Gate 2 obligations. |

### Validation

Reviewed only the diff from `0094306c58f7aa0f5a7f210526f1cd5855f265b4`
to `19f60d2048aa94b1fc749cd44a095363baacc6ef` and collateral contracts
and count/probe boundaries reachable from round 2 findings 1–3. Confirmed the
requested branch and HEAD, an initially clean working tree, and disposition of
all source-round findings. Read the applicable repository instructions and
OpenSpec configuration, checked the revised planning artifacts and searched for
superseded claims. The Gate 1 mechanical floor passed, including strict OpenSpec
validation. This confirms the contract and verification plan, not the partial
implementation. No benchmark, database mutation or implementation test suite was
run. Only `review.md` was modified; no git write commands were run.

## Round 3 · Gate 1
**Reviewer:** codex
**Date:** 2026-09-24
**Reviewed-Commit:** 3c612e47d032c0ae555077769f82d74370fbdf55
**Verdict:** approved

### Findings
| # | Severity | Location | Finding | Status |
|---|----------|----------|---------|--------|
| 1 | minor | design.md, Risks / Trade-offs, scan-bound report | The risk paragraph still dismisses an integration test that forces the scan budget to bite as testing the fixture rather than the service. Task 3.5 now explicitly requires that positive integration path, including an asserted HNSW plan, real candidate retrieval and probe, and a true flag paired with a default-budget false result; `tests/integration/test_search_narrowing.py` also contains that coverage. Replace the stale dismissal with a reference to task 3.5 so the design does not advise abandoning required evidence. This does not block Gate 1 because the task's obligation is explicit and preserved. | fixed |

### Assessment

The renewed requirement permits PostgreSQL to choose a sequential scan for a
narrowed search while retaining the predicate inside the ranking query. The
published plans support the distinction between this complete exact path and
the bounded HNSW path. The delta keeps the unnarrowed index requirement separate
and no longer forbids the newly measured narrowed plan. Task 2.1 checks index
availability under controlled costs; task 3.5 independently requires the
positive bounded-scan regression, so planner freedom does not remove that
verification obligation.

The plan retains pre-offset, pre-threshold candidate counting, separate window
and lookahead bounds, the model/filter/self-bound probe, the full-page limited
case, benchmark isolation and preservation evidence, and the high-tier input
validation obligations. No blocker or major finding was identified in the
Gate 1 contract and verification plan. Implementation correctness and evidence
for checked tasks remain subject to Gate 2.

### Validation

Confirmed branch `change/add-tag-and-meta-filters`, the requested HEAD, and an
initially clean working tree. Read AGENTS.md, openspec/config.yaml, all change
artifacts and prior review records; compared the renewed contract with the
previously confirmed version, the existing text-search specification, the
normative filter requirements and published benchmark output. Inspected the
current count/probe boundary and targeted integration-test references as context.
`scripts/pregate-verify.sh gate1 add-tag-and-meta-filters` passed, including
strict OpenSpec validation, with no warnings. No benchmark, database mutation
or implementation test suite was run. Only `review.md` was modified; no git
write commands were run.

## Round 1 · Gate 2
**Reviewer:** codex
**Date:** 2026-09-24
**Reviewed-Commit:** 9e8506aa5c0f4507f42465bb36144799f885f3d7
**Verdict:** changes-requested

### Findings
| # | Severity | Location | Finding | Status |
|---|----------|----------|---------|--------|
| 1 | blocker | scripts/filter_benchmark.py:341–346, 284–286 | The schema validator accepts `public\n`: Python's `$` matches before a final newline, while the subsequent equality check against `public` does not. SQL treats that newline as whitespace, so the generated statement is `DROP SCHEMA IF EXISTS public CASCADE`. Even though building the copies then fails and rolls back, `run()` executes the same DROP in a new transaction in `finally` and commits it, deleting the service schema and its contents. Reproduced without a database by passing this exact argument through `main()` and recording `run()`'s SQL and transaction exits with a fake engine. Require a full-string identifier match and enforce the protected-schema boundary before either build or cleanup can execute DDL; add a regression for trailing-newline input that proves no database mutation is attempted. | fixed |
| 2 | major | scripts/filter_benchmark.py:100–101, 258–287; docs/how-to/benchmarks.md, schema isolation promise | The benchmark does not establish ownership of its schema: its first operation unconditionally drops whatever already occupies the requested name, and its cleanup drops that name even when setup failed. Thus an otherwise valid `--schema existing_data` destroys that schema's tables, and the default invocation also destroys pre-existing contents of `filter_benchmark`. The name check and the later table-resolution guard cannot protect either case. This is independent of finding 1 and violates the plan's boundary that a run deletes only a schema it created. Use a fresh per-run schema or refuse an existing target before mutation, and make cleanup conditional on successful ownership acquisition. Add preservation tests for an occupied default/custom target and a setup failure, including preservation of assets, embeddings and jobs promised by task 6.1a; the current preservation test checks only asset and embedding identifiers. Reconcile the documented safety claim with the implemented boundary. | fixed |
| 3 | major | openspec/changes/add-tag-and-meta-filters/tasks.md, task 3.1; tests/integration/test_search_narrowing.py:359–398, 488–564 | Task 3.1 is checked, but its required service/repository regression for a scan stopping before OFFSET is absent. The only narrowed integration case with a nonzero offset tests genuine exhaustion and expects false; both positive scan-limit cases use offset zero. The threshold case obtains a lookahead and never probes. Unit tests supply `reached` directly, so they cannot prove that `_page_of` retains the pre-offset count or passes it to the probe/decision when the page is empty. Add the paired limited-before-offset and exhausted-before-offset service regressions promised at Gate 1, assert the actual count/probe bound, and demonstrate failure when the wiring counts after OFFSET or substitutes `offset + reached`. If the chosen real-index corpus cannot reach that condition, use a controlled repository boundary for this service-wiring case and retain the existing real-index positive tests. | fixed |
| 4 | minor | app/services/tagging.py:124; tests/unit/test_narrowing.py | The metadata-key check has the same end-anchor edge case: `parse_narrowing(meta=[('dataset\n', 'coco')])` succeeds and keeps the newline. A URL parameter `meta.dataset%0A=coco` therefore reaches the search instead of producing the promised 422 for characters outside the key alphabet. Use a full-string match and add parser/wire regressions for the terminal newline, including the 64-character boundary. | fixed |

### Validation

Confirmed the requested branch and HEAD and an initially clean working tree.
Read AGENTS.md, OpenSpec configuration, the change artifacts and prior decisions;
reviewed the diff against `main`, including the API/parser, candidate/probe
boundary, listing, UI, benchmark and changed tests and documentation.

All 68 targeted unit tests passed via `make test` using the installed virtual
environment and selecting `test_narrowing.py`, `test_search_cut.py` and
`test_search_policy.py`. Non-mutating Python probes reproduced acceptance of
both newline inputs. A fake connection/engine recorded the benchmark's DROP,
rollback and subsequent committed cleanup DROP; no SQL was sent to a database.

The Gate 2 mechanical floor passed its whitespace, strict OpenSpec, tier,
task-path and documentation-link checks, but its `make check` stage did not
finish in this environment and was interrupted after no further output. A
separate full unit/API run collected 545 selected tests and stalled at
`tests/api/test_asset_upload.py`; it too was interrupted. Consequently this
review does not independently certify the full check suite as green. No
database integration suite, live benchmark or GitHub Actions query was run.
Only `review.md` was modified; no git write commands were run.
