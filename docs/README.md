# Documentation index

Four Diátaxis quadrants plus the decision log. The object-to-location
routing is owned by AGENTS.md ("Documentation Layout"): tutorials,
how-to and reference describe only what exists and works; explanation
may also describe decided design, citing the ADR that decided it.

## Explanation (understanding-oriented)

- [`explanation/requirements.md`](explanation/requirements.md) — the
  technical specification: requirements (FR/NFR ids), data model, API,
  stack, stages; normative for every change

_(architecture and domain model pages arrive with the first
implementing change)_

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

## Reference (facts)

- [`reference/commands.md`](reference/commands.md) — contributor
  command surface: make targets, scripts, agent slash commands
- [`reference/settings.md`](reference/settings.md) — every environment
  variable the service reads, with defaults and the template lines

## Tutorials (learning-oriented)

Empty by design at this stage.

## Decisions (append-only log)

- [`adr/README.md`](adr/README.md) — index of all ADRs with one-line
  decisions
