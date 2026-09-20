# Architecture Decision Records

Append-only log of significant decisions. Superseding a decision means a
new ADR, never editing an old one (AGENTS.md). Copy
[`ADR-TEMPLATE.md`](ADR-TEMPLATE.md) for a new record and add its row
here.

| ADR | Decision in one line |
|---|---|
| [ADR-000](ADR-000-agent-workflow.md) | Agent workflow: Claude executes, Codex reviews at risk-tiered gates, user merges (process, precedes the series) |
| [ADR-001](ADR-001-per-model-vector-index-layout.md) | One embeddings table with an untyped vector column, a CHECK carrying the model allowlist and each width, and one partial HNSW index per model over the dimension cast |
