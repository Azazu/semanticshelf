"""The interface cannot reach the service's own code.

FR-UI-2 says the UI never touches the database or the filesystem; the way it
could is by importing `app`, and then a settings object or a session factory is
one line away. The check is static, so it also catches an import inside a
function — which is exactly how such a shortcut arrives.
"""

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.ui

UI = Path(__file__).resolve().parents[2] / "ui"
FORBIDDEN = "app"


def modules() -> list[Path]:
    return sorted(UI.rglob("*.py"))


def imports_of(path: Path) -> set[str]:
    """Every module this file imports, including inside a function."""
    tree = ast.parse(path.read_text(), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
    return found


def test_nothing_in_the_interface_imports_the_service() -> None:
    offenders = {
        path.name: sorted(name for name in imports_of(path) if name.split(".")[0] == FORBIDDEN)
        for path in modules()
    }

    assert modules(), "the walk found no modules, so it proves nothing"
    assert not {name: found for name, found in offenders.items() if found}


def test_the_walk_reads_the_files_it_claims_to() -> None:
    """The guard above is only as good as the walk, so the walk is checked."""
    names = {path.name for path in modules()}

    assert {"client.py", "shell.py", "app.py", "search.py", "browse.py"} <= names
    assert "httpx" in imports_of(UI / "client.py")
