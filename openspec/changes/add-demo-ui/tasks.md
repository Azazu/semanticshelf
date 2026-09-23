# Tasks — add-demo-ui

## 1. The groups, and what may not be reached

- [ ] 1.1 Add two dependency groups: `ui` (Streamlit) and `screenshots`
  (Playwright), with `uv add --group ui streamlit` and
  `uv add --group screenshots playwright`. Verify: `pyproject.toml` lists both
  as groups rather than runtime dependencies, `make lock-check` passes, and
  `make check` is unchanged in what it installs — the gate floor never sees
  either.
- [ ] 1.2 Settle the multipage entry point against the installed Streamlit
  (`uv pip show streamlit`, then its own documentation for that version), and
  record the answer in `design.md`'s Open Questions as resolved. Verify: the
  version and the chosen entry point are named in the design, and the pages
  render under it in task 4.1.
- [ ] 1.3 `tests/ui/test_layering_ui.py`: nothing under `ui/` reaches `app.`.
  Verify: the test walks the import statements of every module in `ui/`,
  including imports inside functions, and asserts none resolves into the
  service; it also asserts the walk found the modules it claims to have checked.
  Demonstrated failing input: `from app.core.settings import Settings` in a page
  makes it fail.

## 2. The one thing that speaks HTTP

- [ ] 2.1 `ui/client.py`: the base URL from `API_BASE_URL` with the documented
  default, one client with a timeout, and one function per call the pages make
  (search, list assets, read an asset, upload, delete, tags, stats, ready).
  Verify: unit tests under the `ui` marker drive every function through an
  `httpx.MockTransport` and assert the request each one makes — path, query and
  method.
- [ ] 2.2 Every refusal becomes `ServiceError(title, detail)` built from the
  problem details, and a service that cannot be reached becomes one too, with a
  sentence a person can act on. Verify: tests for a 4xx problem-details body, a
  5xx one, a body that is not problem details at all, and a connection error;
  each asserts what the page would show. Demonstrated failing input: returning
  the raw body instead of raising makes the page tests show a status code.
- [ ] 2.3 A picture's address is built by joining the base URL with the
  `links.thumbnail` / `links.file` the API returned, and nothing else. Verify: a
  test asserts the joined address for a relative link and that a link the API
  did not give is never invented.

## 3. The four pages

- [ ] 3.1 **Search**: a description, a grid of thumbnails with scores, the
  `min_score` slider, a tag filter, a "more" button that asks for the next
  `offset`, the model named, and a plain sentence when nothing was found.
  Verify: `AppTest` runs the page against the stub for a search with results, a
  search with none, a threshold that empties the page, and a "more" click that
  asks for the next offset and appends.
- [ ] 3.2 **Browse**: a paginated grid, the tag cloud from `/tags` as a filter,
  an asset's detail with metadata, index status per model and the full-size
  picture, and a delete that asks first. Verify: `AppTest` covers narrowing by a
  tag, opening one asset, and a delete that only calls the API after the
  confirmation — asserted against the stub, which records the requests it was
  asked for.
- [ ] 3.3 **Upload**: a file, tags and metadata, and the service's answer shown
  as it worded it. Verify: `AppTest` covers an accepted upload and a refused one
  (415 problem details), asserting the created asset and the refusal's title and
  detail.
- [ ] 3.4 **Status**: `/ready`, the counts per model and state, the bytes the
  store holds and the age of the oldest waiting work, with "nothing is waiting"
  said plainly rather than as a zero. Verify: `AppTest` covers a ready service,
  one that is not ready (503 problem details with its `checks`), and a store
  with nothing waiting.
- [ ] 3.5 A page whose request fails leaves the rest of the page usable. Verify:
  a test per page asserts that after a failed call the page still renders and
  shows the service's wording.

## 4. Running it

- [ ] 4.1 `make ui` runs the application; `make test-ui` runs the tests of the
  `ui` marker; both say which group to install when it is missing rather than
  failing with an import error. Verify: `make -n ui` and `make -n test-ui` show
  the commands, `make help` lists both, and the marker is registered in
  `pyproject.toml` so an unmarked run does not collect them.
- [ ] 4.2 `pytest.ini` markers and `make check` stay honest: the `ui` tests are
  deselected by the gate floor exactly as `models` and `integration` are.
  Verify: `make check` collects none of them, and its test count changes only by
  what this change adds outside `tests/ui/`.

## 5. The screenshots

- [ ] 5.1 `scripts/screenshots.py`: start the API and the UI on ports it picked,
  wait until each answers, drive Playwright's Chromium at a fixed viewport,
  write `docs/images/search.png`, `browse.png` and `status.png`, and stop both
  children. Verify: `make screenshots` produces the three files against the demo
  corpus, and the images are committed.
- [ ] 5.2 The script leaves nothing running: both children are started in their
  own process group, killed as a group on every exit path including a failure,
  and the script checks they are gone before it returns. Verify: a run followed
  by `ss -ltn` and a process list shows neither server; a run that is
  interrupted mid-way is followed by the same check. Demonstrated failing input:
  removing the cleanup leaves a listening port behind, which the check catches.
- [ ] 5.3 An empty corpus is said, not screenshotted. Verify: running the script
  against an empty store exits with a message naming `make demo`, and writes no
  image.

## 6. Documentation

- [ ] 6.1 `docs/how-to/demo-ui.md`: what each page is for, how to run it
  (`make demo`, `make run`, `make ui`), the one setting, the note that the
  browser fetches pictures from the API directly, and how to produce the
  screenshots including the browser download. Verify: every command in it was
  run in the form shown.
- [ ] 6.2 `AGENTS.md`'s layout line for `ui/` matches what was built, and
  `docs/reference/commands.md` lists the three new make targets. Verify: both
  read as the repository is.

## 7. Evidence

- [ ] 7.1 A real run end to end: `make demo`, `make run`, `make ui`, each page
  opened and used — a search performed, a tag filtered, an asset opened and
  deleted, a picture uploaded — with the screenshots produced from that same
  corpus. Verify: the three images are in `docs/images/`, and the how-to's
  captured output is from that run.
- [ ] 7.2 `make check` and `make test-integration` green the way CI runs them
  (`FORCE_COLOR=1 CI=true`), `make test-ui` green, `openspec validate --all
  --strict`, every `scripts/*_test.sh`, and `sh -n` over `scripts/*.sh`.
