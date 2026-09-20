"""Repositories are the boundary: nothing they expose may be an ORM class.

A returned ORM instance would carry its session with it, and a field access
after the request ended would either emit a query or raise. The frozen domain
objects cannot do either, so the boundary is checked here rather than trusted.
"""

import inspect
import typing
from collections.abc import Iterator

import app.repositories as repositories
from app.db.base import Base


def is_orm(obj: object) -> bool:
    return isinstance(obj, type) and issubclass(obj, Base)


def public_methods() -> Iterator[tuple[str, object]]:
    for class_name in repositories.__all__:
        cls = getattr(repositories, class_name)
        for name, member in inspect.getmembers(cls, inspect.isfunction):
            if not name.startswith("_"):
                yield f"{class_name}.{name}", member


def test_the_package_exports_no_orm_class() -> None:
    exported = [getattr(repositories, name) for name in repositories.__all__]
    assert exported, "the package exports nothing"
    assert not [obj for obj in exported if is_orm(obj)]


def test_no_public_method_returns_an_orm_class() -> None:
    offenders = []
    for qualified_name, method in public_methods():
        hints = typing.get_type_hints(method)
        for part in typing.get_args(hints.get("return")) or (hints.get("return"),):
            if is_orm(part):
                offenders.append(f"{qualified_name} -> {part.__name__}")
    assert not offenders, offenders


def test_every_repository_takes_a_session_and_nothing_else() -> None:
    for class_name in repositories.__all__:
        cls = getattr(repositories, class_name)
        parameters = list(inspect.signature(cls.__init__).parameters)
        assert parameters == ["self", "session"], (class_name, parameters)
