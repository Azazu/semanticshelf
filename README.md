# SemanticShelf

Semantic search over images: CLIP text→image and DINOv2 image→image embeddings in PostgreSQL + pgvector, served by FastAPI.

**Stage:** scaffolded — the FastAPI application skeleton (settings,
structured logs with request ids, RFC 9457 errors, async database
engine, Alembic baseline, liveness and readiness probes, Swagger UI) is in
place; features arrive through reviewed OpenSpec changes
(see `openspec/ROADMAP.md`; the specification is
`docs/explanation/requirements.md`).

## Start reading here

| You want to… | Go to |
|---|---|
| Run the project locally | [docs/how-to/local-development.md](docs/how-to/local-development.md) |
| Look up contributor commands | [docs/reference/commands.md](docs/reference/commands.md) |
| See what is planned | [openspec/ROADMAP.md](openspec/ROADMAP.md) |
| See why any decision was made | [docs/adr/README.md](docs/adr/README.md) |
| See how AI agents work on this repo | [AGENTS.md](AGENTS.md) |
| Browse all documentation | [docs/README.md](docs/README.md) |

## Quick start

```bash
cp .env.example .env
make init      # uv sync (downloads Python 3.12 once), start the database, migrate
make check     # lock check + lint + format check + types + unit and api tests
make run       # http://127.0.0.1:8000/api/docs · /health · /ready
```

## Licence

MIT — see [LICENSE](LICENSE).
