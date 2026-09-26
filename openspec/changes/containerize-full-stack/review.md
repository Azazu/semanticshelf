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

## Confirmation 1 · Gate 1 · Round 2
**Reviewer:** codex
**Date:** 2026-09-26
**Reviewed-Commit:** 477fe3bc2d396f29b3246a1f55e115a523b9888b
**Verdict:** changes-requested

### Findings
| # | Resolution |
|---|------------|
| 1 | changes-requested — Decision 1 and tasks 1.3–1.4 now specify a separate `--only-group ui` build and explicit checks that `app` and `torch` are absent. But the same architecture is still contradicted by `proposal.md`'s Impact section, which calls the UI image "the service plus the demo UI", and `design.md`'s Risks section, which says the UI image is a thin layer on the runtime image. Reconcile those collateral claims with the separate build. |

## Confirmation 2 · Gate 1 · Round 2
**Reviewer:** codex
**Date:** 2026-09-26
**Reviewed-Commit:** bac6396da16085329d847d0fa77d9ea9f220fa0c
**Verdict:** confirmed

### Findings
| # | Resolution |
|---|------------|
| 1 | confirmed — The proposal's Impact section and the design's Risks section now describe two separate environments, matching design decision 1, tasks 1.3–1.4, and the Dockerfile's independent `ui-builder` and `ui` stages. The tasks explicitly verify that `app` and `torch` are absent from the UI image. |

## Round 1 · Gate 2
**Reviewer:** codex
**Date:** 2026-09-26
**Reviewed-Commit:** 7d41566556e569af56933361f5d34763582d3140
**Verdict:** changes-requested

### Findings
| # | Severity | Location | Finding | Status |
|---|----------|----------|---------|--------|
| 1 | major | `.env.example:10-12`; `scripts/stack-env.sh:44-50`; `docs/how-to/local-development.md:13-17` | The new setup generates a 32-character `DB_PASSWORD` but replaces only the `__GENERATED__` marker. `DATABASE_URL` in the same template still contains `localdev-only-password`, so the documented `sh scripts/stack-env.sh` followed by `make init` starts PostgreSQL with one password and runs Alembic with another. A fresh local-development checkout fails to migrate, and a host API started from that file cannot connect. Generate a matching host `DATABASE_URL` (including the configured user, database and port), and verify the documented host setup from a clean checkout. | fixed |
| 2 | minor | `docs/how-to/running-the-stack.md:61-64`; `docker-compose.yml:63-103` | The how-to says setting `HF_HUB_OFFLINE=1` in the environment file stops the containers from contacting the Hub, but Compose does not pass that variable to `api`, `worker`, or the one-shot warm command. The environment file only supplies values referenced by the Compose file; this setting is not referenced, and the image does not contain the file. Wire it into the relevant container environments or correct the instruction, then verify the offline setting inside a container. | fixed |

## Confirmation 1 · Gate 2 · Round 1
**Reviewer:** codex
**Date:** 2026-09-26
**Reviewed-Commit:** 779c5e8f3a0f4575255a46d0c4c32b46ff21d575
**Verdict:** changes-requested

### Findings
| # | Resolution |
|---|------------|
| 1 | changes-requested — The committed template now puts the generated password in both fields, and the recorded clean-checkout run verifies the default values. But the host `DATABASE_URL` still hardcodes `semanticshelf` as user and database and `5433` as port. `scripts/stack-env.sh` checks only that the URL contains the generated password. For example, setting `FORWARD_DB_PORT=5444` publishes PostgreSQL on 5444 while the host migration still connects to 5433; changing `DB_USER` or `DB_NAME` likewise leaves the URL pointed at the old values. Generate or validate the URL against all configured database fields and the published host port, then verify a nondefault configuration. |
| 2 | confirmed — `HF_HUB_OFFLINE` is passed through the shared environment mapping used by `api`, `worker`, and the one-shot warm command; the how-to now shows the setting, and tasks.md records verification inside a container. |

## Confirmation 2 · Gate 2 · Round 1
**Reviewer:** codex
**Date:** 2026-09-26
**Reviewed-Commit:** 39a3e1106799d424d3ac5edc9532f906a69b02df
**Verdict:** confirmed

### Findings
| # | Resolution |
|---|------------|
| 1 | confirmed — `scripts/stack-env.sh` now composes the host `DATABASE_URL` from the generated password and the written `DB_USER`, `DB_NAME`, and `FORWARD_DB_PORT`, with an environment port override when supplied. Isolated checks matched all four fields for nondefault values, a port override, and a template without a URL line; a missing user was refused without a target file. Task 11.3 records a clean checkout migration and successful `/ready` with a nondefault user, database, and port. |
| 2 | confirmed — The offline setting remains passed to the relevant containers; the reviewed changes do not alter the resolution confirmed in Confirmation 1. |
