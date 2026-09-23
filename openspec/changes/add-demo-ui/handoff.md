# Handoff — add-demo-ui

**Updated:** 2026-09-23 · claude
**State:** fixing-g2
**Branch:** change/add-demo-ui

## Done this session

Branch, scaffold and all four planning artifacts. Two decisions the user made
before anything was written:

- **The screenshots are automated in this change**, not left for a person: a
  script brings up the API and the UI against the demo corpus, drives a headless
  browser and writes the three images the roadmap asks this change for.
- **The UI tests get their own `ui` marker**, run by `make test-ui` after
  `uv sync --group ui`, exactly as `models` and `integration` keep heavy
  dependencies out of the gate floor. CI will not run them until CI is taught
  to, and that is verifier infrastructure — `high` tier, its own change.

Decided in the proposal rather than inherited:

- **Tier `medium`**, raised from the roadmap's `low`: this adds a second
  application, two dependency groups, a browser-driven step and a page that
  deletes assets on a click. It touches nothing in the service, which is why it
  is not `high`.
- **The "Find similar" page is out of scope.** FR-UI-1 names five pages;
  `/similar` and image search arrive with DINOv2 in change 11, and that page
  arrives with them. This change delivers the four the roadmap names.

## Next step

**Security-sensitive** (AGENTS.md): this change adds dependencies and uploads a
file, and it deletes assets irreversibly from a page. That is what raised the
tier to `high`.

Gate 2 round 1 returned eight findings — seven major, one minor — and every one
was real.

1. **The tier was wrong.** `AGENTS.md` puts a change touching file uploads or
   dependencies at `high`, whatever the reasoning about the service. Raised, the
   applicability table added, and Gate 1 is owed on the artifacts.
2-7. **Streamlit's execution model.** A page draws itself and only then runs the
   code that changes state, so a click showed its effect one interaction late: a
   page of results that appeared after some unrelated click, a tag change that
   asked for the new tag at the old offset, a delete that left the picture on
   screen, a refusal that destroyed the results a person already had, paging
   that used whatever was typed rather than what was searched, and a "More" that
   disappeared exactly when a filter had emptied the page. Each is now
   state-then-rerun, with a snapshot of what was asked kept beside the results,
   and each has a test that asserts what is *rendered* after one click.
8. **The cleanup promise was stronger than the code.** Stopping a screenshot
   server returned as soon as the leader had exited, which says nothing about
   the child holding the port. The group id is kept and the group itself is
   checked, with a test for a child that outlives its leader.

The earlier tests all passed because they asserted the requests a page made —
which every one of these defects got right.

Run: `/gate-review add-demo-ui 1` (the tier now demands it), then the Gate 2
confirmation. The user pushes first — the code changed.

Local evidence, the way CI runs it (`FORCE_COLOR=1 CI=true`): `make check` 408
green, `make test-integration` 198 green, `make test-ui` 35 green, strict
validation 14/14. Seven demonstrated failing inputs, one per fix.

## Blockers

None.
