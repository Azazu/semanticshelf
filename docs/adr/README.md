# Architecture Decision Records

Append-only log of significant decisions. Superseding a decision means a
new ADR, never editing an old one (AGENTS.md). Copy
[`ADR-TEMPLATE.md`](ADR-TEMPLATE.md) for a new record and add its row
here.

| ADR | Decision in one line |
|---|---|
| [ADR-000](ADR-000-agent-workflow.md) | Agent workflow: Claude executes, Codex reviews at risk-tiered gates, user merges (process, precedes the series) |
| [ADR-001](ADR-001-per-model-vector-index-layout.md) | One embeddings table with an untyped vector column, a CHECK carrying the model allowlist and each width, and one partial HNSW index per model over the dimension cast |
| [ADR-002](ADR-002-vector-index-family-and-parameters.md) | HNSW at `m = 16`, `ef_construction = 64` stays for every model, measured against IVFFlat: recall@10 1.000 at the shipped effort, and IVFFlat has no strict iterative order for a narrowed search |
| [ADR-003](ADR-003-queue-in-postgresql.md) | The indexing queue is the `indexing_jobs` table claimed with `FOR UPDATE SKIP LOCKED`, owned by a lease whose expiry is the claim's token, and made repeat-safe by the upsert — no broker |
| [ADR-004](ADR-004-claims-restricted-to-named-assets.md) | A claim may name the assets whose work it wants, so a runner that created work can finish it; every other claim is unchanged, and the queue stays first due, first served |
