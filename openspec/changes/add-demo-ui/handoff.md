# Handoff — add-demo-ui

**Updated:** 2026-09-23 · claude
**State:** proposing
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

All 20 tasks. The interface exists, runs against the real service, and the three
screenshots in `docs/images/` were taken from it on the demo corpus — not drawn,
not cropped by hand.

What the work found that the plan could not:

- The gate floor would have gone red in CI the moment `tests/ui/` was collected,
  because collection imports a test module before deciding to deselect it and
  Streamlit is in a group CI does not install. The directory is now ignored when
  the group is absent, and that was verified by pruning the group
  (`uv run --exact`) and running the floor's own selection: 406 tests, the UI
  directory not looked at.
- The first `make ui` asked for an email address and blocked — Streamlit's
  onboarding. The target runs headless and prints the address instead.
- The integration suite empties the store, so the corpus has to be re-indexed
  before capturing screenshots. The how-to says so, and the script refuses an
  empty store rather than writing three pictures of nothing — checked by
  emptying it.

Evidence: `make check` 406 green and `make test-integration` 198 green, both
under `FORCE_COLOR=1 CI=true`; `make test-ui` 31 green; `openspec validate --all
--strict` 14/14; both `scripts/*_test.sh`; `sh -n` over every script. Five
demonstrated failing inputs: importing `app` from a page, returning a refusal
instead of raising it, paging from a fixed offset, deleting without the
confirmation, and removing the screenshot script's cleanup (which leaves a
server running — the probe killed what it leaked).

The user pushes, then Gate 2: `/gate-review add-demo-ui 2`.

## Blockers

None.
