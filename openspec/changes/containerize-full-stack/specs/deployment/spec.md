## Purpose
What the delivered system is, rather than what the service does: the image the
service ships in, the stack that runs it as separate processes, what survives a
restart, and what is exposed to whom.

## ADDED Requirements

### Requirement: One command brings the whole system up

The repository SHALL carry a container stack that starts the complete system —
the database, the schema at its current head, the API, the process that carries
out indexing work, and the demo interface — from a clean checkout with one
command and no manual step between them.

A service SHALL NOT start before what it needs is ready: the schema SHALL be
brought to head before the API serves, and the worker and the interface SHALL
start against an API that has reported itself ready. Readiness SHALL be decided
by asking the service, never by waiting a fixed time.

The stack SHALL NOT require the person running it to have the language runtime,
its package manager or a virtual environment on the host.

#### Scenario: A clean checkout
- **WHEN** the stack is started in a checkout that has never been run
- **THEN** the database is created and migrated, the API answers ready, the
  interface is reachable, and nothing else had to be done first

#### Scenario: Readiness decides the order
- **WHEN** the database is slow to accept connections, or the schema is not yet
  at head
- **THEN** the API is not started until both are true, and the failure of either
  shows as that service not being healthy rather than as a crash loop in the one
  that depends on it

#### Scenario: A picture uploaded to the stack becomes searchable
- **WHEN** a picture is uploaded to the API of the running stack
- **THEN** it is stored, its work is queued, the separate worker process carries
  that work out, and the picture is afterwards found by a search — with no
  extraction having run inside the API process

### Requirement: The image carries the service and nothing else

The runtime image SHALL contain the application, its locked runtime
dependencies and nothing whose only use is development: no test framework, no
linter, no type checker, and not the demo interface's own dependencies. The
interface SHALL be built as its own image from the same file, so that a
deployment that does not want it does not ship it.

The image SHALL NOT contain model weights. They are fetched into a cache the
stack holds outside the image, and the repository SHALL provide a command that
fills that cache without serving a request.

The environment inside the image SHALL be resolved from the same lock file the
tests and CI use, so that what is deployed is what was checked.

The service SHALL NOT run as the superuser inside the image, and the paths it
writes to SHALL be limited to the volumes the stack gives it.

#### Scenario: What is in the image
- **WHEN** the runtime image is inspected
- **THEN** the application and its runtime dependencies are present, the
  development and interface dependencies are not, and no model weights are in it

#### Scenario: The same lock file
- **WHEN** the image is built
- **THEN** its dependencies are resolved from the repository's lock file without
  being allowed to move, so a build cannot quietly differ from what CI tested

#### Scenario: Not the superuser
- **WHEN** a container of the runtime image is inspected while running
- **THEN** the process belongs to an unprivileged user, and the media root and
  model cache it must write to are writable by that user

### Requirement: State outlives the containers

The media the service stores, the vectors and rows the database holds, and the
model weights fetched on first use SHALL live in volumes rather than inside a
container's writable layer. Stopping and starting the stack SHALL find all three
where they were.

The media root SHALL be the same storage for the API and for the worker, because
one writes what the other reads.

#### Scenario: A restart keeps the corpus
- **WHEN** the stack is stopped and started again
- **THEN** the assets, their files, their vectors and the cached weights are all
  still there, and nothing is re-downloaded or re-indexed

#### Scenario: The worker reads what the API wrote
- **WHEN** a picture is uploaded to the API and the worker extracts its vectors
- **THEN** the worker reads the bytes the API stored, from the same media root

### Requirement: In the stack, the runner is the worker

The stack SHALL be configured so that the process serving requests carries out
no extraction work: a request queues it, and the separate worker process
executes it. The service's own switch for choosing the runner SHALL be what
decides this, rather than a second mechanism invented for the stack.

#### Scenario: The API queues and does not extract
- **WHEN** a picture is uploaded to the stack and the worker is stopped
- **THEN** the upload still succeeds and its work stays queued until the worker
  runs again, rather than being carried out by the API

### Requirement: Nothing is exposed beyond loopback unless a deployment says so

Every port the stack publishes SHALL bind to the loopback address by default,
and the address SHALL be a single setting a deployment can change deliberately.
The documentation SHALL state what the service does and does not protect, and
what publishing it further would require.

#### Scenario: Default publication
- **WHEN** the stack is started without changing any setting
- **THEN** its ports are reachable from the host that runs it and from nowhere
  else

### Requirement: The image is built by CI and scannable by a published command

Continuous integration SHALL build the runtime image on every change, so that a
build broken by a dependency or a file that stopped being copied is found by the
same run that finds a failing test.

The repository SHALL carry a command that scans the built image for known
vulnerabilities and fails on findings of high or critical severity that have a
fix available. The scanner SHALL be pinned to a version, and the command SHALL
NOT publish the image anywhere.

#### Scenario: CI builds it
- **WHEN** a change is pushed
- **THEN** the image is built from the repository as it stands, and a build
  failure fails the run

#### Scenario: The scan reports what it found
- **WHEN** the scan command is run against the built image
- **THEN** it reports the vulnerabilities found by severity, and exits non-zero
  when a fixable one of high or critical severity is present
