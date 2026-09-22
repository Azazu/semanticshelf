"""The service never reaches the module that reaches the network.

NFR-SEC-4 promises that the API and the worker make no outbound request except
the model download. The demo corpus command is the one place in this repository
that fetches from a public dataset, and a promise nothing checks is a comment.

The check is static rather than dynamic on purpose. Asking `sys.modules` after
building the application answers only "was it imported *by this call*", which is
false even when a router imports it at module level; and it cannot see an import
written inside a function, which is exactly how an unwanted dependency arrives.
Reading the import statements answers the question that matters: can anything
the service loads reach this module at all.
"""

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[2] / "app"
ENTRY = "app.main"
FORBIDDEN = "app.services.demo_dataset"


def module_path(name: str) -> Path | None:
    parts = name.split(".")[1:]
    if not parts:  # `app` itself
        return PACKAGE / "__init__.py" if (PACKAGE / "__init__.py").is_file() else None
    relative = Path(*parts)
    for candidate in (PACKAGE / relative.with_suffix(".py"), PACKAGE / relative / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def imports_of(path: Path) -> set[str]:
    """Every `app.…` module this file imports, including inside a function."""
    tree = ast.parse(path.read_text(), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names if alias.name.startswith("app."))
        elif isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("app"):
            found.add(node.module)
            found.update(f"{node.module}.{alias.name}" for alias in node.names)
    return found


def reachable_from(entry: str) -> set[str]:
    seen: set[str] = set()
    pending = [entry]
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        path = module_path(name)
        if path is None:  # a name imported *from* a module, not a module itself
            continue
        seen.add(name)
        pending.extend(imports_of(path) - seen)
    return seen


def test_the_application_cannot_reach_the_demo_module() -> None:
    reachable = reachable_from(ENTRY)

    assert ENTRY in reachable, "the walk found nothing, so it proves nothing"
    assert FORBIDDEN not in reachable, (
        f"{FORBIDDEN} is reachable from {ENTRY}: the service would carry the one module "
        "that fetches from the internet"
    )


def test_the_walk_sees_what_the_application_really_imports() -> None:
    """The guard above is only as good as the walk, so the walk is checked."""
    reachable = reachable_from(ENTRY)

    assert {"app.api.search", "app.services.search", "app.repositories.embeddings"} <= reachable
