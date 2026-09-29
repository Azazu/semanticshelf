## MODIFIED Requirements

### Requirement: Readiness probe
The service SHALL answer `GET /ready` with HTTP 200 and `{"status": "ready", "checks": {"database": "ok", "migrations": "ok", "models": "ok", "revisions": "ok", "media": "ok"}}` only when every check passes. Otherwise it SHALL answer HTTP 503 as problem details (`application/problem+json`, the members required by the HTTP API conventions) with `type` `/errors/not-ready` and an extension member `checks` holding one line per check: `ok`, or a reason. A reason MUST be built from exception class names, a timeout statement, the revision comparison, the model comparison, the checkpoint-revision comparison, the state of the media root or the skip statement — never from an exception message, so no connection string, host, user or credential can appear in it, and never a filesystem path, which is deployment information a probe has no reason to publish. The checks are: `database` — `SELECT 1` on the configured database completes within `READINESS_TIMEOUT_SECONDS` (default 3); `migrations` — the database's Alembic revision equals the code's head revision, queried under the same time budget; `models` — every enabled embedding model key is declared by the database's dimension constraint with the width the application declares for it, so a deployment whose schema and whose model registry disagree is caught before it writes a vector; `revisions` — for every enabled storage model the store holds a record for, the recorded checkpoint revision equals the configured one, so a deployment whose corpus was built with different weights is caught before it ranks them against each other; `media` — the configured media root exists, is a directory and is writable, and the location uploads are received into lies outside it, so a deployment that cannot store a picture, or that would expose an upload in progress to `storage prune`, is not sent traffic. The `migrations`, `models` and `revisions` checks are skipped with the reason `skipped: database check failed` when the database check failed; the `media` check does not depend on the database and SHALL run in every case. No check SHALL block the event loop, and the probe MUST NOT load any model: it compares declarations, never weights. It MUST answer within about twice the configured timeout in every case.

#### Scenario: Database reachable and migrated
- **WHEN** the database answers `SELECT 1` within the timeout, its Alembic revision is the code's head, the schema declares every enabled model with the width the application declares, every recorded checkpoint revision equals the configured one, and the media root is a writable directory
- **THEN** `GET /ready` is 200 with all five checks `ok`

#### Scenario: Database refuses connections
- **WHEN** the database refuses connections
- **THEN** `GET /ready` is 503 `application/problem+json` with `type` `/errors/not-ready`, `checks.database` naming the exception class, `checks.migrations`, `checks.models` and `checks.revisions` equal to `skipped: database check failed`, `checks.media` reporting the media root's own state, and no host, user, credential or URL anywhere in the body

#### Scenario: Database is silent
- **WHEN** the database accepts the connection but never answers
- **THEN** `GET /ready` is 503 within about the configured timeout, `checks.database` states the timeout (`TimeoutError: no response within <timeout>s`) and the database-dependent checks are skipped

#### Scenario: Migrations behind the code
- **WHEN** the database is reachable but its Alembic revision differs from the code's head (including no revision at all)
- **THEN** `GET /ready` is 503 with `checks.database` `ok` and `checks.migrations` stating the database revision and the expected head

#### Scenario: Schema and model registry disagree
- **WHEN** the application enables a model key or a width that the database's dimension constraint does not declare
- **THEN** `GET /ready` is 503 with `checks.models` naming the key and the two widths, and no model has been loaded

#### Scenario: The corpus was built with a different checkpoint
- **WHEN** the store holds a recorded checkpoint revision for an enabled model key and the configured revision for that key is a different one
- **THEN** `GET /ready` is 503 with `checks.revisions` naming the key and both revisions, and no model has been loaded

#### Scenario: The corpus predates the record
- **WHEN** the store's record for an enabled model key reads `unknown`
- **THEN** `GET /ready` is 503 with `checks.revisions` naming the key and stating that the corpus's provenance was never recorded, so an operator is told rather than served a silent guess

#### Scenario: A key the store holds no vectors for
- **WHEN** an enabled model key has no record because the store holds no vector under it
- **THEN** the `revisions` check does not fail on that key: there is nothing whose provenance could disagree

#### Scenario: The media root is missing, read-only, or holds the receipt location
- **WHEN** the configured media root does not exist, is not a directory, is not writable, or contains the location uploads are received into
- **THEN** `GET /ready` is 503 with `checks.media` stating which of those is the case, without quoting the path
