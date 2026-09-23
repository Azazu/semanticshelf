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
