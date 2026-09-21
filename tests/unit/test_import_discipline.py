"""The model runtime stays out of the import path.

`torch` and `transformers` together weigh a few hundred megabytes and take
seconds to import. Every test run, every `--help` and every request that never
touches a model would pay for it, so nothing under `app/` may import them while
being imported itself: the adapter imports them inside the functions that use
them.
"""

import ast
import subprocess
import sys
from pathlib import Path

HEAVY = frozenset({"torch", "transformers"})
APP = Path(__file__).resolve().parents[2] / "app"


def _is_type_checking(test: ast.expr) -> bool:
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


def runtime_imports(node: ast.AST) -> set[str]:
    """The top-level packages a module imports merely by being imported.

    A function body is skipped: it runs when it is called. A `TYPE_CHECKING`
    block is skipped too — it never runs at all. A class body is not skipped,
    because it executes at import like any other statement.
    """
    names: set[str] = set()
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if isinstance(child, ast.If) and _is_type_checking(child.test):
            continue
        if isinstance(child, ast.Import):
            names |= {alias.name.split(".")[0] for alias in child.names}
        elif isinstance(child, ast.ImportFrom):
            if child.level == 0 and child.module:
                names.add(child.module.split(".")[0])
        else:
            names |= runtime_imports(child)
    return names


def test_the_walker_sees_what_it_claims_to_see() -> None:
    # Without this, a broken walker would report every module as clean.
    assert runtime_imports(ast.parse("import torch")) == {"torch"}
    assert runtime_imports(ast.parse("from torch import nn")) == {"torch"}
    assert runtime_imports(ast.parse("class A:\n    import torch")) == {"torch"}
    assert runtime_imports(ast.parse("def f():\n    import torch")) == set()
    assert runtime_imports(ast.parse("if TYPE_CHECKING:\n    import torch")) == set()


def test_no_module_under_app_imports_the_model_runtime_when_imported() -> None:
    offenders = {
        str(path.relative_to(APP.parent)): sorted(heavy)
        for path in sorted(APP.rglob("*.py"))
        if (heavy := runtime_imports(ast.parse(path.read_text(encoding="utf-8"))) & HEAVY)
    }
    assert offenders == {}


def test_importing_the_application_does_not_pull_the_model_runtime_in() -> None:
    # The static check above reads our own code; this one is the fact itself,
    # and would catch a third package dragging the runtime in behind us.
    program = (
        "import sys; import app.main; "
        "print(sorted(name for name in sys.modules if name in ('torch', 'transformers')))"
    )
    finished = subprocess.run(
        [sys.executable, "-c", program], capture_output=True, text=True, check=True
    )
    assert finished.stdout.strip() == "[]"
