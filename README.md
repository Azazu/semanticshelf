# SemanticShelf

Semantic search over images: CLIP text→image and DINOv2 image→image embeddings in PostgreSQL + pgvector, served by FastAPI.

**Stage:** scaffold — agent workflow, documentation layout and CI are
in place; application code arrives through reviewed OpenSpec changes
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
make init      # build containers, install dependencies, migrate
make check     # lint + static analysis + tests
```
