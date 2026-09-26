"""The dependency rule, read out of the import graph.

NFR-QA-2 asks for layering to be enforced where it is cheap: routers hold no SQL
and call no model, the model layer knows nothing about storage, repositories
hand back domain objects rather than the API's own shapes, and `app/domain.py`
depends on nothing that could drag a framework into it. Three narrower checks
already exist — the service never reaches the demo-dataset module
(`test_layering_demo.py`), no repository returns an ORM class
(`test_repositories_layering.py`), nothing imports the model runtime at import
time or a measurement command at all (`test_import_discipline.py`). This is the
general one.

It reads **every** import, including those written inside functions: an import
in a function body is exactly how an unwanted dependency arrives, and it is
invisible to anything that only looks at a module's header.

Where a rule has an exception, the exception is named here with its reason. A
rule with an unexplained hole is a rule that erodes.
"""

import ast
from dataclasses import dataclass, field
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2] / "app"


@dataclass(frozen=True)
class Rule:
    """One arrow that may not exist in the import graph."""

    whose: str
    may_not_reach: tuple[str, ...]
    because: str
    #: Module -> why that one module is allowed the import anyway.
    except_in: dict[str, str] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return f"{self.whose} → {', '.join(self.may_not_reach)}"


RULES: tuple[Rule, ...] = (
    Rule(
        whose="app.api",
        may_not_reach=("app.db",),
        because="a router that opens its own session has taken the schema for itself",
        except_in={
            "app.api.deps": "the wiring module: its whole job is handing a session to a router",
        },
    ),
    Rule(
        whose="app.api",
        may_not_reach=("app.ml",),
        because="a model call in a request handler is the thing the inference pool exists to prevent",
    ),
    Rule(
        whose="app.ml",
        may_not_reach=("app.db", "app.repositories", "sqlalchemy"),
        because="the model layer knows what a vector is and nothing about where it is kept",
    ),
    Rule(
        whose="app.repositories",
        may_not_reach=("app.schemas", "app.api"),
        because="a repository returns domain objects; the API's own shapes belong above it",
    ),
    Rule(
        whose="app.services",
        may_not_reach=("app.api",),
        because="a service that imports a router has the arrow backwards",
    ),
    Rule(
        whose="app.domain",
        may_not_reach=("fastapi", "sqlalchemy", "pydantic", "app.db", "app.api", "app.services"),
        because="every layer may depend on the vocabulary, so the vocabulary depends on none of them",
    ),
)

#: What `app.api` may take from SQLAlchemy: the *types* a dependency and a
#: handler annotate with, and the factory the wiring module builds sessions
#: with. Never `select`, `text` or anything else that could make a query — which
#: is what "routers contain no SQL" means in practice, since a router that
#: cannot name a query cannot build one.
DATABASE_NAMES_ROUTERS_MAY_TAKE = frozenset({"AsyncSession", "AsyncEngine", "async_sessionmaker"})


def modules() -> dict[str, Path]:
    """Every module of the application, by its dotted name."""
    found = {}
    for path in sorted(APP.rglob("*.py")):
        relative = path.relative_to(APP.parent).with_suffix("")
        parts = [part for part in relative.parts if part != "__init__"]
        found[".".join(parts)] = path
    return found


def imports_of(path: Path) -> set[str]:
    """Every module this one imports, anywhere in it.

    Function bodies included, on purpose: `import app.db` inside a handler is
    the same dependency as one at the top, and only harder to see.
    """
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module)
    return names


def names_imported_from(path: Path, package: str) -> set[str]:
    """What a module takes *by name* out of a package."""
    taken: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if node.module == package or node.module.startswith(package + "."):
                taken |= {alias.name for alias in node.names}
    return taken


def reaches(imported: str, target: str) -> bool:
    return imported == target or imported.startswith(target + ".")


def within(module: str, layer: str) -> bool:
    return module == layer or module.startswith(layer + ".")


def test_the_walker_sees_what_it_claims_to_see(tmp_path: Path) -> None:
    # Without this, a broken walker would report every module as clean.
    sample = tmp_path / "sample.py"
    sample.write_text(
        "import app.db\nfrom app.ml import registry\n\n"
        "def later():\n    from app.repositories import assets\n",
        encoding="utf-8",
    )
    assert imports_of(sample) == {"app.db", "app.ml", "app.repositories"}
    assert names_imported_from(sample, "app.ml") == {"registry"}


def test_every_rule_is_about_modules_that_exist() -> None:
    """A rule over a layer nobody wrote passes without ever looking at code."""
    known = modules()
    for rule in RULES:
        assert any(within(module, rule.whose) for module in known), rule.whose
        for exempt in rule.except_in:
            assert exempt in known, exempt


@pytest.mark.parametrize("rule", RULES, ids=lambda rule: rule.name)
def test_the_arrow_does_not_exist(rule: Rule) -> None:
    offenders = []
    for module, path in modules().items():
        if not within(module, rule.whose) or module in rule.except_in:
            continue
        for imported in sorted(imports_of(path)):
            for target in rule.may_not_reach:
                if reaches(imported, target):
                    offenders.append(f"{module} imports {imported}")
    assert offenders == [], f"{rule.because}. Found: {offenders}"


def test_a_router_may_hold_the_type_of_a_session_and_not_the_means_to_query() -> None:
    """ "Routers contain no SQL" as something a check can answer: a handler may
    name the session it is given, and may not name anything that builds or runs
    a statement."""
    taken: dict[str, set[str]] = {}
    for module, path in modules().items():
        if not within(module, "app.api"):
            continue
        names = names_imported_from(path, "sqlalchemy")
        if names:
            taken[module] = names

    assert taken, "no router imports anything of SQLAlchemy, so this check is asserting nothing"
    for module, names in taken.items():
        beyond = names - DATABASE_NAMES_ROUTERS_MAY_TAKE
        assert beyond == set(), f"{module} takes {sorted(beyond)} from SQLAlchemy"
