# Handoff — add-demo-ui

**Updated:** 2026-09-23 · claude
**State:** merged
**Branch:** change/add-demo-ui
**Security-sensitive:** yes — this change adds dependencies (two groups:
Streamlit and Playwright), uploads a file from a page, and deletes assets
irreversibly on a person's click. `AGENTS.md` puts each of those at `high` tier
and asks for the flag here and in the commit bodies.

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

- **Tier `high`.** The roadmap declared `low` and this change was first proposed
  as `medium`, on the reasoning that it touches nothing in the service. Gate 2
  rejected that reasoning and was right to: `AGENTS.md` puts a change touching
  file uploads or dependencies at `high` whatever else is true of it, and this
  one also deletes assets irreversibly. The tier was corrected during the change,
  the applicability table added, and Gate 1 run retrospectively (`approved`).
- **The "Find similar" page is out of scope.** FR-UI-1 names five pages;
  `/similar` and image search arrive with DINOv2 in change 11, and that page
  arrives with them. This change delivers the four the roadmap names.

## Next step

Merged into `main` as `cbfa9d3` (`--no-ff`, 11 commits) and archived with its
delta synced: `demo-ui` joins `openspec/specs/` as a new capability of five
requirements.

Next in the roadmap: stage 3 opens with change 11, `add-dinov2-image-search` —
and with it the fifth page FR-UI-1 names, "Find similar", which this change
deliberately left out.

## Blockers

None.
