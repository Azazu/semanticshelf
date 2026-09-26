# Documentation index

Four Diátaxis quadrants plus the decision log. The object-to-location
routing is owned by AGENTS.md ("Documentation Layout"): tutorials,
how-to and reference describe only what exists and works; explanation
may also describe decided design, citing the ADR that decided it.

## Explanation (understanding-oriented)

- [`explanation/architecture.md`](explanation/architecture.md) — how it is put
  together: the four processes and what each is not allowed to do, the request
  path, the job path, where things are stored, what is deliberately absent, and
  where the layering is enforced
- [`explanation/requirements.md`](explanation/requirements.md) — the
  technical specification: requirements (FR/NFR ids), data model, API,
  stack, stages; normative for every change

_(the data model has one home, §3 of the specification; a second description of
it would be the duplication this layout exists to prevent)_

## How-to (task recipes)

- [`how-to/local-development.md`](how-to/local-development.md) — run the
  project locally (setup, daily commands, reset, troubleshooting)
- [`how-to/local-mcp.md`](how-to/local-mcp.md) — wire the IDE's MCP
  endpoint for Claude Code
- [`how-to/models.md`](how-to/models.md) — the embedding models: what is
  downloaded, where it is cached, warm-up, offline runs, tuning
- [`how-to/uploading.md`](how-to/uploading.md) — uploading a picture: what is
  accepted and refused, the headers, the listing, deletion, and finding
  orphan files
- [`how-to/indexing.md`](how-to/indexing.md) — the indexing queue: the state
  of an asset's work, finding what failed and why, and running it again
- [`how-to/searching.md`](how-to/searching.md) — the three ways to ask: words,
  a picture you send, a picture the store holds. What a score means, paging and
  its depth bounds, thresholds, which model answers, and how to narrow a search
  by tags and metadata
- [`how-to/running-the-stack.md`](how-to/running-the-stack.md) — the whole
  system in containers: one command, the five services and what each waits for,
  the volumes and what survives, the ports and what they do not mean, the images
  and the scan
- [`how-to/demo-ui.md`](how-to/demo-ui.md) — the Streamlit demo: what each page
  does, how to run it against a service somewhere else, and how the screenshots
  are made
- [`how-to/benchmarks.md`](how-to/benchmarks.md) — two measurements: which plan
  answers a narrowed search at which selectivity, and what the vector index
  gives up — recall@10 against an exact ranking, the `ef_search` curve, HNSW
  against IVFFlat, per model

## Reference (facts)

- [`reference/commands.md`](reference/commands.md) — contributor
  command surface: make targets, scripts, agent slash commands
- [`reference/settings.md`](reference/settings.md) — every environment
  variable the service reads, with defaults and the template lines
- [`reference/demo-dataset.md`](reference/demo-dataset.md) — where the demo
  corpus comes from, which licences are accepted and why, and how attribution is
  given

## Tutorials (learning-oriented)

Empty by design at this stage.

## Decisions (append-only log)

- [`adr/README.md`](adr/README.md) — index of all ADRs with one-line
  decisions
