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
