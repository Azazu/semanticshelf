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
