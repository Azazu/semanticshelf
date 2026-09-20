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
The service SHALL answer `GET /ready` with HTTP 200 and `{"status": "ready", "checks": {"database": "ok", "migrations": "ok"}}` only when every check passes, and otherwise with HTTP 503 and `{"status": "not-ready", "checks": {...}}` where each failed check carries a short reason (an exception class name or a one-line cause) and never a connection string, a credential or a stack trace. The checks are: `database` — `SELECT 1` on the configured database completes within `READINESS_TIMEOUT_SECONDS` (default 3); `migrations` — the database's Alembic revision equals the code's head revision. The probe MUST NOT load any model.

#### Scenario: Database reachable and migrated
- **WHEN** the database answers `SELECT 1` within the timeout and its Alembic revision is the code's head
- **THEN** `GET /ready` is 200 with both checks `ok`

#### Scenario: Database unreachable
- **WHEN** the database refuses connections or does not answer within the timeout
- **THEN** `GET /ready` is 503 with `checks.database` naming the cause and no credential in the body

#### Scenario: Migrations behind the code
- **WHEN** the database is reachable but its Alembic revision differs from the code's head (including no revision at all)
- **THEN** `GET /ready` is 503 with `checks.migrations` stating the database revision and the expected head

### Requirement: Probes live outside the versioned API
Both probes SHALL be served at `/health` and `/ready`, outside the `/api/v1` prefix, and SHALL appear in the OpenAPI document with a summary and a description.

#### Scenario: Probe paths
- **WHEN** a client reads the OpenAPI document
- **THEN** it lists `/health` and `/ready` with their response schemas, and no probe path starts with `/api/v1`
