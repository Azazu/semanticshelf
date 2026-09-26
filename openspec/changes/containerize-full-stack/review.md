# Review — containerize-full-stack

## Round 1 · Gate 1
**Reviewer:** codex
**Date:** 2026-09-26
**Reviewed-Commit:** 7f9a538cfef79640a502ddd4bae2151c558e9208
**Verdict:** changes-requested

### Findings
| # | Severity | Location | Finding | Status |
|---|----------|----------|---------|--------|
| 1 | major | `specs/deployment/spec.md:8-26`; `design.md:30-41,55`; `tasks.md:30-50` | The clean-checkout, one-command requirement has no configuration path. `docker-compose.yml` requires `DB_NAME`, `DB_USER`, and `DB_PASSWORD` through `:?required`, while `.env` is ignored and only `.env.example` is committed. A fresh checkout therefore stops during Compose interpolation before any service starts. Specify how the stack obtains working local defaults without a manual copy step, and add an exact clean-checkout verification task. | fixed |
| 2 | major | `design.md:40-41,144-151`; `tasks.md:42-47` | The plan does not set the container-side `DATABASE_URL` for `migrate`, `api`, and `worker`. The existing `.env.example` URL addresses `127.0.0.1:5433`, which is the host-published database port; inside each container that address is its own loopback, so migrations and readiness cannot succeed. Define a URL using `db:5432` for all three services and verify each process connects with the host port overridden. | fixed |
| 3 | major | `design.md:144-151`; `tasks.md:42-47,86-88` | `API_BASE_URL=http://api:8000` lets the UI server call the API, but `ui/client.py:54-61` also uses it to construct image URLs passed to `st.image` in `ui/shell.py` and the pages. A host browser cannot resolve Compose's `api` service name, so the UI's corpus images will not render; a `curl -sI` of the UI port will miss this. Design a browser-reachable asset URL that works with `APP_PORT` overrides and loopback binding, then verify an image renders through the published UI. | fixed |

## Confirmation 1 · Gate 1 · Round 1
**Reviewer:** codex
**Date:** 2026-09-26
**Reviewed-Commit:** 37e66bad8760e24ae57e29742b3e315e3342bd8f
**Verdict:** changes-requested

### Findings
| # | Resolution |
|---|------------|
| 1 | confirmed — `make stack` creates the ignored configuration from the committed template, generates the password, and preserves required-variable failures. Tasks 8.1–8.2 require an exact fresh-clone run, repeat run, and missing-value failure. |
| 2 | changes-requested — decision 10b assigns `db:5432` to `migrate`, `api`, and `worker`, but task 8.3 checks only migration and API readiness with `FORWARD_DB_PORT` overridden. The worker indexing run in task 5.2 overrides `APP_PORT` and `UI_PORT`, not `FORWARD_DB_PORT`; no task verifies that the worker connects and completes a job while the host database port is overridden. Add that verification to the plan. |
| 3 | confirmed — decision 10c separates the UI's internal API address from the browser's published address using `APP_PORT`; tasks 8.4–8.5 cover the default and split settings and assert a rendered thumbnail in a browser, including a failing case with the internal name. The `demo-ui` delta updates the affected requirement. |

## Confirmation 2 · Gate 1 · Round 1
**Reviewer:** codex
**Date:** 2026-09-26
**Reviewed-Commit:** 6445c0dd7925339cbcec08e1b7ed3d5fdf360b72
**Verdict:** confirmed

### Findings
| # | Resolution |
|---|------------|
| 1 | confirmed — The clean-checkout configuration path and its verification remain as confirmed in Confirmation 1; the reviewed changes do not affect them. |
| 2 | confirmed — Tasks 5.2 and 8.3 now require the same run with `FORWARD_DB_PORT` overridden to prove migration, API readiness, and completion of an uploaded picture's jobs by the worker with the API runner disabled. Decision 10b records this shared verification. |
| 3 | confirmed — The browser-reachable image address and rendered-thumbnail verification remain as confirmed in Confirmation 1; the reviewed changes do not affect them. |

## Round 2 · Gate 1
**Reviewer:** codex
**Date:** 2026-09-26
**Reviewed-Commit:** cb49897b3d8a8497d9097563381fe9507e5b3cc8
**Verdict:** changes-requested

### Findings
| # | Severity | Location | Finding | Status |
|---|----------|----------|---------|--------|
| 1 | major | `design.md:64-71`; `tasks.md:13-23`; `proposal.md:35-41` | The revised proposal promises a separate UI image built with `--only-group ui`, without the application or model runtime, but design decision 1 still says the UI target extends the runtime stage and task 1.3 still directs adding the UI group to that target. Following the design and task would put the application and model dependencies in the UI image, reversing the stated isolation and size decision. Reconcile the design and task with the separate UI build, and make the UI image's exclusion of `app` and the model runtime an explicit verification task. | fixed |
