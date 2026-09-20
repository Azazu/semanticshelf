# SemanticShelf

Semantic search over images: CLIP text→image and DINOv2 image→image embeddings in PostgreSQL + pgvector, served by FastAPI.

**Stage:** specified — agent workflow, documentation layout, CI and the
technical specification (`docs/explanation/requirements.md`) are in
place; application code arrives through reviewed OpenSpec changes
(see `openspec/ROADMAP.md`).

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
make check     # lock check + lint + format check + types + unit tests
```

## Licence

MIT — see [LICENSE](LICENSE).
