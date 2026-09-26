## MODIFIED Requirements

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
