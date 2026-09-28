# http-api-conventions Specification

## Purpose
The contract every endpoint shares: a request id that ties a response to its log lines, one machine-readable error format for every failure, and a discoverable OpenAPI document with Swagger UI.

## Requirements

### Requirement: Request id on every response
The service SHALL attach a request id to every request: the value of the `X-Request-ID` request header when it is present and matches `^[A-Za-z0-9._-]{1,128}$`, otherwise a freshly generated UUID4. The id SHALL be returned in the `X-Request-ID` response header on every response, including errors, and SHALL be bound to every log line written while handling the request.

#### Scenario: Client-supplied id
- **WHEN** a request carries `X-Request-ID: abc-123`
- **THEN** the response carries `X-Request-ID: abc-123` and the log lines of that request contain `request_id=abc-123`

#### Scenario: Missing or invalid id
- **WHEN** a request carries no `X-Request-ID`, or one longer than 128 characters or with characters outside the allowed set
- **THEN** the response carries a generated UUID4 in `X-Request-ID` and the client-supplied value is not echoed

### Requirement: Problem details for every error
Every response with a status of 400 or higher SHALL have the media type `application/problem+json` and a body with `type` (`about:blank` for plain HTTP errors, a stable `/errors/<slug>` reference for domain errors), `title`, `status`, `detail` and `instance` equal to `urn:request:<request-id>`. Validation failures SHALL be 422 with `type` `/errors/validation` and an `errors` array of `{loc, msg, type}` objects; the client's input values MUST NOT be echoed. An unhandled exception SHALL produce 500 with `title` `Internal Server Error`, an empty `detail`, no exception text, and exactly one log record at error level carrying the request id and the traceback.

#### Scenario: Unknown route
- **WHEN** a client requests a path that does not exist
- **THEN** the response is 404 `application/problem+json` with `type` `about:blank`, `title` `Not Found`, `status` 404 and `instance` naming the request id

#### Scenario: Validation failure
- **WHEN** a request fails Pydantic validation
- **THEN** the response is 422 `application/problem+json` with `type` `/errors/validation` and an `errors` array whose objects carry only `loc`, `msg` and `type`

#### Scenario: Unhandled exception
- **WHEN** a handler raises an exception the application does not map
- **THEN** the response is 500 `application/problem+json` with no exception text, and one error-level log record with the request id and the traceback exists

### Requirement: OpenAPI document and Swagger UI
The service SHALL serve the OpenAPI 3.1 document at `/api/openapi.json` and Swagger UI at `/api/docs`; ReDoc is not served. Every operation SHALL carry a summary and a description, and the document SHALL declare the problem-details response for the error statuses an operation can return.

Every operation SHALL also carry an example of what it answers, and that example
SHALL parse as the thing it illustrates: an example that is not a valid answer
is worse than no example, because a reader trusts it. An operation that has
nothing to exemplify is exempt and only for that reason — an answer with no body
at all, or one whose body is bytes rather than a document — and the exemption
SHALL be recorded where the rule is checked rather than left to whoever reads
the document next.

#### Scenario: Documentation paths
- **WHEN** a client requests `/api/openapi.json` and `/api/docs`
- **THEN** the first is a valid OpenAPI 3.1 document whose `info.version` is the application version and the second is an HTML page; `/api/redoc` is 404

#### Scenario: Every operation shows what it answers
- **WHEN** the document is read for an operation that answers with a body
- **THEN** that operation carries a summary, a description and an example, and
  the example is a valid answer of that operation — checked against the model
  the service answers with, not merely present

#### Scenario: An operation with nothing to exemplify
- **WHEN** an operation answers with no body, or with bytes rather than a
  document
- **THEN** it carries no example, and the reason it carries none is written
  where the rule is enforced

### Requirement: Structured logs with request context
The service SHALL write one JSON object per log line to stdout with at least `timestamp`, `level`, `event` and, for lines written while handling a request, `request_id`, `method` and `path`. When `LOG_JSON` is false the same records are rendered for a terminal instead. Log records MUST NOT contain request bodies, credentials or the database URL.

#### Scenario: JSON log line for a request
- **WHEN** the service handles a request with `LOG_JSON` true
- **THEN** each log line written during that request is a JSON object containing `request_id`, `method` and `path`
