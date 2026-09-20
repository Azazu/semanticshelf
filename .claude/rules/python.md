## Python / FastAPI specifics
- Run everything through `uv run …` (or `make …`); never `pip install`
  into the system interpreter; dependencies change only via
  `uv add` / `uv remove` so `uv.lock` stays authoritative
- Verify library APIs against the installed version (`uv pip show <pkg>`,
  the package source under `.venv/`) — FastAPI, SQLAlchemy 2 and
  pgvector APIs changed across majors
- Never load a real ML model in tests, tools or import paths; use
  `app/ml/fake.py`
- `make check` before claiming a task done
