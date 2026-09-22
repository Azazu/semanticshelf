# Review — add-text-to-image-search

## Round 1 · Gate 2
**Reviewer:** codex
**Date:** 2026-09-22
**Reviewed-Commit:** e61bb8eab2e2c31308871ce70adbb1a20c45dda1
**Verdict:** changes-requested

### Findings
| # | Severity | Location | Finding | Status |
|---|----------|----------|---------|--------|
| 1 | major | `app/repositories/embeddings.py:124`; `openspec/changes/add-text-to-image-search/design.md:84` | Pagination is applied in the inner query before the UUID tie-break: `ORDER BY distance LIMIT/OFFSET` chooses an arbitrary subset of an equal-distance group, and the outer `ORDER BY distance, asset_id` can only sort that already-chosen subset. When a tie straddles a page boundary, repeated requests or adjacent pages can therefore swap, duplicate, or omit tied assets instead of using the identifier as the global tie-break required by `specs/text-search/spec.md`. Design decision 7 explicitly accepts this case, so it is a known contract violation rather than merely a missing test; the existing tie tests keep both tied rows on one page and cannot expose it. | wont-fix — a global identifier tie-break is not implementable over an approximate index: measured on 10 005 vectors, at the default `ef_search = 40` the index returns 1 of 5 exactly-tied rows, so no window and no `FETCH FIRST … WITH TIES` can order rows that are not in the candidate set (design decision 7). The requirement was corrected to what the index can promise and goes back through Gate 1; the user arbitrated on 2026-09-22 after the third confirmation. |

## Confirmation 1 · Gate 2 · Round 1
**Reviewer:** codex
**Date:** 2026-09-22
**Reviewed-Commit:** 6a292f27cfa9fc716234aa1fdbf2f471937735da
**Verdict:** changes-requested

### Findings
| # | Resolution |
|---|------------|
| 1 | changes-requested — the new window still executes `ORDER BY distance LIMIT offset + limit` without the UUID tie-break, so it may choose a different subset of an equal-distance group before the outer query orders and cuts the page. This preserves the named swap/duplicate/omission defect and also cannot guarantee the revised specification's unconditional promise that repeated requests for one page return the same items. The added tests only observe one PostgreSQL plan returning the same arbitrary subset several times; they do not enforce a total order before the window limit. The specification's new permission for arbitrary division across pages therefore does not resolve the finding, and the retained per-page repeatability claim remains unsupported. |

## Confirmation 2 · Gate 2 · Round 1
**Reviewer:** codex
**Date:** 2026-09-22
**Reviewed-Commit:** 3b42d089a6e369a488e591cb714239dbe70b6caa
**Verdict:** changes-requested

### Findings
| # | Resolution |
|---|------------|
| 1 | changes-requested — the implementation still cuts an index-selected `LIMIT offset + limit` window before applying the UUID tie-break, and the revised specification now permits the same cross-page repeats and omissions named in Round 1 instead of implementing the original global tie-break. That contract change is not coherent across the change artifacts: `proposal.md` still promises unconditionally that identifier tie-breaking makes a page stable while the index is unchanged, while the revised spec and how-to disclaim stable membership when a page edge cuts an equal-score group. Under the repository's fix-the-claim rule, the surviving scope claim means the finding is not resolved. |

## Confirmation 3 · Gate 2 · Round 1
**Reviewer:** codex
**Date:** 2026-09-22
**Reviewed-Commit:** 480276762e9a1316245f95ba4f207f1540a576ef
**Verdict:** changes-requested

### Findings
| # | Resolution |
|---|------------|
| 1 | changes-requested — the implementation still applies `LIMIT offset + limit` before the UUID tie-break, so separate page windows may select different members of a tie and retain the Round 1 duplicate/omission defect. The artifacts are now textually consistent only because they weaken the requirement to permit that defect; this is a requirements/architecture change that does not implement the original global tie-break and would reopen Gate 1 under `AGENTS.md`. Its stated justification is also false: equal cosine scores do not require bit-identical vectors, because distinct vectors can have the same cosine distance from a query. The named finding is therefore not resolved. |

## Round 1 · Gate 1
**Reviewer:** codex
**Date:** 2026-09-22
**Reviewed-Commit:** 38de0bf0b59eb2c902bacefd0837ce31769dbbef
**Verdict:** changes-requested

### Findings
| # | Severity | Location | Finding | Status |
|---|----------|----------|---------|--------|
| 1 | blocker | `specs/embedding-storage/spec.md:6,20-22`; `specs/text-search/spec.md:71-85`; `design.md:95-115` | The revised tie contract was not propagated to the embedding-storage delta. That delta still requires an offset lookup to be the tail of the unpaged answer with unchanged order, while the text-search spec and design explicitly permit the index-selected windows for adjacent pages to repeat or omit members when an equal-distance group crosses a boundary. The planned statement therefore cannot satisfy both requirements. The storage requirement and its verification task must carry the same bounded guarantee as the search contract, or the architecture must provide the unconditional tail behavior they currently require. | open |
| 2 | blocker | `specs/text-search/spec.md:125-170`; `design.md:46-76`; `tasks.md:10,20-21` | `has_more` requires looking one candidate beyond the page, and decision 4 says the index window grows for that extra candidate, but search effort is only `max(HNSW_EF_SEARCH, limit + offset)` and is capped at 1000. Once the requested depth controls the effort, the statement needs `limit + offset + 1` candidates while the index is provisioned for only `limit + offset`; at the explicitly accepted depth of 1000, the required sentinel is at depth 1001, which the design says cannot be requested. Thus the artifacts do not define an implementable `has_more` guarantee at the boundary (and under-provision its sentinel on other deep pages). Reconcile the searchable bound, effort calculation, and `has_more` semantics, with verification at the exact boundary. | open |
| 3 | major | `proposal.md:43-47`; `specs/service-stats/spec.md:3-15`; `design.md` decision 10; `tasks.md:27-29` | The proposal promises “bytes under the media root” and the capability spec describes disk occupied by pictures, but the design and tasks sum recorded `size_bytes` for originals and explicitly exclude thumbnails and any filesystem reconciliation. Those are different metrics when thumbnails exist, files are missing, or orphan files remain. Choose whether `/stats` reports physical media-root usage or logical original-byte totals, then use that meaning consistently in the proposal, spec, design, task, and endpoint documentation. | open |
| 4 | major | `docs/explanation/requirements.md` FR-OPS-4; `tasks.md:18,27-29` | FR-OPS-4 requires every operation to have an OpenAPI example, but the tasks for the three new operations verify only response shape, summary, and description. There is no implementation task or verification task for examples on `/search/text`, `/tags`, or `/stats`, so the Gate 1 definition of ready is not met for this inherited mandatory requirement. Add explicit task coverage and evidence for the examples. | open |
