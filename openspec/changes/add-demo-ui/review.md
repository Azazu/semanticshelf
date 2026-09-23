# Review — add-demo-ui

## Round 1 · Gate 2
**Reviewer:** codex
**Date:** 2026-09-23
**Reviewed-Commit:** 890da452bcbfe963fb51bb364b8be6faed42fe69
**Verdict:** changes-requested

### Findings

| # | Severity | Location | Finding | Status |
|---|----------|----------|---------|--------|
| 1 | major | openspec/changes/add-demo-ui/proposal.md:3 | The declared medium tier bypasses required Gate 1 review. AGENTS.md explicitly makes changes touching dependencies high tier; this change adds Streamlit and Playwright, and also implements upload and irreversible deletion actions. Being an HTTP client does not exempt it from those rules. Raise the tier, reconcile the design applicability/evidence and security-sensitive handoff requirements, and obtain the required Gate 1 decision (or explicit user waiver) before completing the gates. | fixed — tier raised to `high`, applicability table added, Gate 1 requested |
| 2 | major | ui/pages/search.py:43–58; ui/pages/browse.py:33–50 | Pagination updates state after rendering, without triggering another render. AppTest shows that one More click leaves only the first thumbnail displayed although results now contains two items; one Next page click still requests offset 0 although browse_offset becomes 12. The next page is only visible after an unrelated interaction, and repeated clicks can advance state beyond what is displayed. Process paging before fetching/rendering or rerun after a successful state transition. Test the rendered next page immediately after one click, including the final page. | fixed |
| 3 | major | ui/pages/browse.py:25–33 | Changing the tag does not reset browse_offset, and the page offers no way back. After Next page, selecting a tag with one matching asset requests that tag at offset 12, shows an empty-store message, and strands the user even though a match exists. Reset pagination and the selected asset when the filter changes; provide a route back to earlier pages. Add a test that filters after advancing beyond the first page. | fixed |
| 4 | major | ui/pages/browse.py:64–70 | Successful deletion leaves the deleted asset's thumbnail, full-size image and selected detail on screen. Both views were rendered before DELETE; assigning session_state.opened does not clear the unkeyed Open selectbox that actually controls the detail. AppTest confirms two image elements and selection 1 remain alongside the success message. Clear the actual selection and confirmation state, refresh the listing/tags and rerender after deletion, handling an emptied last page. Assert that the deleted asset is absent immediately after confirmation, as the delta spec requires. | fixed |
| 5 | major | ui/pages/search.py:23–31 | A new search clears results and offset before the request succeeds. A 422 or unavailable service therefore destroys the previous successful results, contrary to the explicit refusal scenario in the delta spec. AppTest reproduces a successful search followed by a 422 leaving zero images and an empty results list. Commit replacement search state only after success; test that a refused replacement preserves the previous results and pagination. | fixed |
| 6 | major | ui/pages/search.py:46–51 | More uses the current widget values rather than the parameters that produced the accumulated results. Searching for cat, editing the query to dog without pressing Search, and pressing More sends dog at offset 12 and appends it to cat results. Threshold and tag edits have the same problem. Store the submitted query/filter snapshot with the results and use it for paging, or explicitly reset/restart the search when those inputs change. Test that edits cannot mix result sets or skip the new query's first page. | fixed |
| 7 | major | ui/pages/search.py:40–44; ui/client.py:101–104 | More is nested under if results, but client-side tag filtering can empty the first API page while has_more remains true. AppTest confirms this produces only a Search button with has_more=true; matching assets on later pages are unreachable. Render paging independently of whether the accumulated filtered results are nonempty, and distinguish an empty current page from exhausted results. Test an unmatched first page followed by a matching later page. | fixed |
| 8 | minor | scripts/screenshots.py:81–96 | The cleanup guarantee is stronger than its implementation. _stop returns immediately when the leader has exited, and after process.wait succeeds it never checks whether other members of the process group remain. A surviving descendant is therefore neither verified nor necessarily killed, despite task 5.2 and the design claiming the whole group is checked. Retain the process-group identifier and verify/escalate cleanup for the group even when the leader exits; cover a descendant that outlives its leader. | fixed |

### Verification

- Confirmed the requested branch and HEAD and read the change artifacts, repository instructions, config, implementation, tests and diff against main.
- Ran `.venv/bin/python -B -m pytest tests/ui -m ui -p no:cacheprovider -q`: **31 passed**. These tests do not assert the failing state transitions above.
- Ran in-memory AppTest reproductions using the existing MockTransport stub for findings 2–7; no test files were added or modified.
- Full gate-floor, integration and browser screenshot runs were not repeated during this review. Finding 8 is based on source inspection.

## Round 1 · Gate 1
**Reviewer:** codex
**Date:** 2026-09-23
**Reviewed-Commit:** 3f8b6dd96aee85e700dc786e969e348237414b20
**Verdict:** approved

### Findings

| # | Severity | Location | Finding | Status |
|---|----------|----------|---------|--------|
| 1 | minor | openspec/changes/add-demo-ui/design.md: Decisions 3; openspec/changes/add-demo-ui/specs/demo-ui/spec.md: Search shows what was found and how well | Document the search tag filter as a client-side filter of fetched ranking pages. The current API accepts no tag parameter, and ui/client.py filters returned items locally; consequently a page can be empty while later pages contain matches, and has_more describes the unfiltered ranking. Task 3.6 already covers that case, but the design's claim that the grid never fetches more than it shows and the spec's wording about not fetching and hiding results obscure this deliberate limitation. Reconcile the design/spec/how-to wording while retaining the existing offset and empty-page verification. | open |
| 2 | minor | openspec/changes/add-demo-ui/design.md: Goals and Decision 6 | Narrow the claimed reach guarantee to what the proposed mechanism establishes. Walking UI import statements for app imports guards the direct service-code dependency; it does not prove that the UI cannot access a database, filesystem or model through another library or a dynamic import. Keep the HTTP-only architectural requirement, but identify source review as the verification for those other restrictions and state the static test's limits rather than describing it as a capability boundary. | open |

### Verification

- Confirmed branch `change/add-demo-ui`, the requested HEAD and an initially clean working tree.
- Read AGENTS.md, openspec/config.yaml, all change artifacts, the roadmap and relevant normative requirements; checked the existing search API and the UI client/import guard to assess the proposed mechanisms.
- The high tier is appropriate; the applicability table and implementation/verification task coverage support the four-page scope, with image search explicitly deferred to change 11. No blocker or major design finding identified.
- Ran `scripts/pregate-verify.sh gate1 add-demo-ui`: passed, including strict OpenSpec validation, with zero warnings.
- This is the retrospective Gate 1 artifact review required by the tier correction. It does not confirm the earlier Gate 2 findings or replace the required Gate 2 confirmation; application tests and browser runs were not repeated here.
