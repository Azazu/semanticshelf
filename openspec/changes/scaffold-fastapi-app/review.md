# Review — scaffold-fastapi-app

## Round 1 · Gate 2
**Reviewer:** codex
**Date:** 2026-09-20
**Reviewed-Commit:** cb1b1435d56b3734a2dbe5eae4c800ad4bc3fd41
**Verdict:** changes-requested

### Findings
| # | Severity | Location | Finding | Status |
|---|----------|----------|---------|--------|
| 1 | major | `app/api/health.py:45-56`; `tests/api/test_health.py:25-34`; `openspec/changes/scaffold-fastapi-app/specs/http-api-conventions/spec.md:18-19` | The not-ready path constructs a plain `JSONResponse`, and its OpenAPI declaration uses `ReadyResponse`; the resulting 503 has `Content-Type: application/json` and only `status`/`checks`. This violates the change's SHALL that every response at status 400 or higher is `application/problem+json` with `type`, `title`, `status`, `detail`, and the request-bound `instance`. The tests currently assert the nonconforming body without checking the global error contract, and the health-probes and HTTP-conventions artifacts must be reconciled so the intended 503 representation is unambiguous. | open |
| 2 | major | `app/services/readiness.py:29-31,42-43,63-64`; `openspec/changes/scaffold-fastapi-app/specs/health-probes/spec.md:18-27` | `describe()` publishes the first line of an arbitrary database exception verbatim; truncating it does not remove a connection string or credential. For example, `describe(RuntimeError("postgresql+asyncpg://dbuser:supersecret@db/semanticshelf"))` returns that complete URL, contradicting the readiness requirement that a failure reason never expose a connection string or credential. Use an allow-listed/redacted diagnostic and add a failing-input test containing URL/user/password material for both database-check paths. | open |
| 3 | major | `app/api/health.py:51-54`; `app/services/readiness.py:34-44,57-64`; `openspec/changes/scaffold-fastapi-app/specs/health-probes/spec.md:25-27` | When the database does not answer, `check_database()` times out as configured, but `ready()` then always opens a second connection in `check_migrations()`, which has no timeout. A black-holed database can therefore leave `/ready` waiting on the driver's independent/default connect timeout instead of returning the required 503 after detecting the configured timeout. Skip the migration query after database failure or apply a bounded budget to it, and cover the non-responding case rather than only connection refusal on port 1. | open |
