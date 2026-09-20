## Purpose

Liveness and readiness probes that let a container orchestrator, a Compose healthcheck and a developer tell "the process runs" apart from "the service can serve": readiness verifies the database and the migration state without loading any model.

## ADDED Requirements

### Requirement: Liveness probe
The service SHALL answer `GET /health` with HTTP 200 and the JSON body `{"status": "ok", "version": "<application version>"}` without touching the database, the filesystem or any model. The version MUST equal the installed package version.

#### Scenario: Process is up
- **WHEN** a client requests `GET /health`
- **THEN** the response is 200 with `status` equal to `ok` and `version` equal to the application version, and no database connection is opened

#### Scenario: Database is down
- **WHEN** the database is unreachable and a client requests `GET /health`
- **THEN** the response is still 200 with `status` equal to `ok`

### Requirement: Readiness probe
The service SHALL answer `GET /ready` with HTTP 200 and `{"status": "ready", "checks": {"database": "ok", "migrations": "ok"}}` only when every check passes. Otherwise it SHALL answer HTTP 503 as problem details (`application/problem+json`, the members required by the HTTP API conventions) with `type` `/errors/not-ready` and an extension member `checks` holding one line per check: `ok`, or a reason. A reason MUST be built from exception class names, a timeout statement, the revision comparison or the skip statement — never from an exception message, so no connection string, host, user or credential can appear in it. The checks are: `database` — `SELECT 1` on the configured database completes within `READINESS_TIMEOUT_SECONDS` (default 3); `migrations` — the database's Alembic revision equals the code's head revision, queried under the same time budget, and skipped with the reason `skipped: database check failed` when the database check failed. The probe MUST NOT load any model and MUST answer within about twice the configured timeout in every case.

#### Scenario: Database reachable and migrated
- **WHEN** the database answers `SELECT 1` within the timeout and its Alembic revision is the code's head
- **THEN** `GET /ready` is 200 with both checks `ok`

#### Scenario: Database refuses connections
- **WHEN** the database refuses connections
- **THEN** `GET /ready` is 503 `application/problem+json` with `type` `/errors/not-ready`, `checks.database` naming the exception class, `checks.migrations` equal to `skipped: database check failed`, and no host, user, credential or URL anywhere in the body

#### Scenario: Database is silent
- **WHEN** the database accepts the connection but never answers
- **THEN** `GET /ready` is 503 within about the configured timeout, `checks.database` states the timeout (`TimeoutError: no response within <timeout>s`) and `checks.migrations` is skipped

#### Scenario: Migrations behind the code
- **WHEN** the database is reachable but its Alembic revision differs from the code's head (including no revision at all)
- **THEN** `GET /ready` is 503 with `checks.database` `ok` and `checks.migrations` stating the database revision and the expected head

### Requirement: Probes live outside the versioned API
Both probes SHALL be served at `/health` and `/ready`, outside the `/api/v1` prefix, and SHALL appear in the OpenAPI document with a summary and a description; the readiness probe's 503 SHALL be documented as a problem-details response.

#### Scenario: Probe paths
- **WHEN** a client reads the OpenAPI document
- **THEN** it lists `/health` and `/ready` with their response schemas, the 503 of `/ready` under the `application/problem+json` media type, and no probe path starts with `/api/v1`
