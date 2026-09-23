# Design — add-demo-ui

## Context

See `proposal.md` — Why. What the design has to work with:

- The API already answers everything the four pages need: `GET /search/text`
  (scores, `min_score`, `limit`/`offset`, `has_more`, the model key),
  `GET /assets` (tags and index-status filters, `has_more`), `GET /assets/{id}`,
  `POST /assets`, `DELETE /assets/{id}`, `GET /tags`, `GET /stats`, `GET /ready`,
  and `links.file` / `links.thumbnail` on every asset.
- Every refusal the service gives is RFC 9457 problem details with a `title` and
  a `detail` written for a person — the UI has nothing to invent.
- `make demo` fills a machine with a corpus, so the pages have something to show
  on a clean checkout.
- The repository already has one rule about reach: a module the service must not
  load is proved unreachable by a static walk of the import statements
  (`tests/unit/test_layering_demo.py`, change 9). The same shape answers "the UI
  never imports the service".

## Goals / Non-Goals

Goals beyond the proposal's scope statement:

- A person who has run `make demo` and `make ui` can search, browse, upload and
  read the service's state without knowing the API exists.
- Nothing in `ui/` can reach the database, the media root, a model, or the
  service's own code — and that is checked rather than intended.
- The screenshots are produced by one command, so they can be produced again
  when a page changes.

Non-goals at the design level: styling beyond Streamlit's defaults, any state
that outlives a browser session, and any behaviour that depends on more than one
person using it at a time.

## Decisions

1. **One client module, and it is the only thing that speaks HTTP.**
   `ui/client.py` holds the base URL (from `API_BASE_URL`, defaulting to
   `http://127.0.0.1:8000`), one `httpx.Client` with a timeout, and one function
   per call the pages make. Every response passes through one place that either
   returns the parsed body or raises `ServiceError(title, detail)` built from the
   problem details. A page therefore never sees a status code, and the rule
   "show the refusal as the service worded it" has exactly one implementation.
   Rejected: calling `httpx` from each page — five places to forget the timeout
   in, and five ways to render an error.

2. **Pictures are addressed, not fetched.** An asset carries
   `links.thumbnail` and `links.file`; the UI joins them with the base URL and
   hands the result to `st.image`, so the *browser* fetches the bytes straight
   from the API. The UI never holds a picture in memory and never learns where
   anything is stored. It also means the API must be reachable from the browser
   and not only from the UI process, which is true for a local demo and is what
   the how-to says.
   Rejected: proxying the bytes through the UI — it would double the traffic and
   invent a second way to serve a picture.

3. **Paging is the API's, not the page's.** "More" asks for the next `offset`
   and appends; the grid never fetches more than it shows. `has_more` decides
   whether the button exists. The same for browsing. This keeps the UI honest
   about what the service promised in change 8: a page is what was asked for.

4. **State lives in `st.session_state`, and only what a page needs**: the query,
   the threshold, the chosen tag, the accumulated results and the asset being
   looked at. Nothing is cached across sessions, because a demo that shows a
   stale corpus after `make demo` would be worse than a slow one.

5. **The smoke tests drive the real pages with a stubbed service.**
   `streamlit.testing.v1.AppTest` runs each page module in-process, and the
   client's transport is replaced with an `httpx.MockTransport` that answers
   with recorded bodies — the same technique the demo corpus tests use. They
   live in `tests/ui/` under a `ui` marker and run with `make test-ui` after
   `uv sync --group ui`, which is how `models` and `integration` already keep
   heavy dependencies out of the gate floor.
   Rejected: driving the pages through a browser for the smoke tests — slow, and
   it would test Chromium rather than the pages.

6. **Reach is proved, not promised.** A test walks the import statements of
   every module under `ui/` and asserts that none of them reaches `app.` — the
   walk change 9 wrote, pointed the other way. It catches an import inside a
   function, which is how a shortcut to `app.core.settings` would arrive.

7. **The screenshots are a script, and the script cleans up after itself.**
   `scripts/screenshots.py` starts the API and the UI on ports it picked, waits
   until each answers, drives Playwright's Chromium at a fixed viewport, writes
   `docs/images/{search,browse,status}.png`, and stops both. Both children are
   started in their own process group and killed as a group, and the script
   checks they are gone before it exits — a server left running after a
   screenshot run is exactly the mistake this repository has already paid for
   once this month.
   Rejected: a recipe in the how-to for a person to follow — it rots the first
   time a page moves, and the roadmap asks this change for the images.

8. **Two dependency groups, neither in the gate floor.** `ui` carries Streamlit,
   `screenshots` carries Playwright. `make check` installs neither, the API
   image ships neither, and `make ui`, `make test-ui` and `make screenshots` say
   which group they need when it is missing rather than failing with an import
   error.

## Applicability

| Question | Answer |
|---|---|
| Crash around an external effect | The interface makes one request at a time and holds nothing of its own: a page that dies mid-request loses the page, not data. The two effects that reach the store are upload and delete, and both are the API's — a person sees either the service's answer or its refusal, and a reload asks the service what is there now rather than trusting what was drawn. The screenshot script is the other side of this: it starts two servers, and stops the whole process group of each on every exit path, verified rather than assumed. |
| Deletion / expiry | Deleting is the only irreversible thing a person can do here. It asks first, deletes through the API exactly as `curl` would, and then the page is rebuilt from the service — the deleted picture, its detail and the confirmation are gone because the listing was fetched again, not because they were hidden. |
| Empty / zero / null inputs | An empty store, a search that matches nothing, a threshold that empties a page, a tag that empties every page fetched so far, a corpus with no tags, and a service that answers nothing at all: each is a sentence a person can act on rather than an empty grid, and paging stays reachable when a filter empties the page it was applied to. |
| Idempotent retries | Every page is a fresh read: searching again re-asks, paging asks for the next offset of the search that produced what is shown, and a repeated upload is the service's duplicate rule (409), shown as the service words it. Nothing here retries by itself. |
| Concurrent writers | n/a — one person, one browser session, and no state of the interface's own beyond what that session is looking at. A second person deleting something shows up as the service's 404 on the next read. |
| Authorization boundary | n/a — the service has no authentication (D12) and the interface has no privileges of its own: it can ask for exactly what `curl` can. The README already says the service belongs behind something that does have an opinion about who is asking. |
| Money rounding | n/a. |

## Risks / Trade-offs

- **Streamlit's API moves between versions** → the pages use its documented
  basics (`st.image`, `st.button`, `st.session_state`, the multipage entry
  point) and the version is pinned by the lock file; the smoke tests fail loudly
  if a page stops rendering.
- **Playwright needs a browser binary** (`playwright install chromium`, a
  download of a few hundred megabytes) → it lives in its own group, is never
  needed by `make check`, and the how-to says so before the first run.
- **The screenshots depend on the corpus** → the script runs against
  `.data/demo`, which `make demo` produces; with an empty corpus it says so
  instead of writing an empty grid.
- **A demo with a delete button** → it deletes through the API, with a
  confirmation, exactly as `curl` would. There is no authentication anywhere in
  this project (D12), and the README already says the service belongs behind
  one.

## Migration Plan

Nothing to migrate: no schema, no data, no API change. A deployment that never
runs the UI is unaffected, and the two new groups are not installed unless
asked for.

## Open Questions

None. The one there was — which multipage entry point to use — was settled
against the installed version during implementation: **Streamlit 1.64.0**, which
has `st.navigation` and `st.Page`. So `ui/app.py` declares the four pages
explicitly and each page is a plain module under `ui/pages/`, rather than
relying on the directory convention's filename ordering. `streamlit.testing.v1`
provides `AppTest`, which is what the smoke tests drive a page module with.
