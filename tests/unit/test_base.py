"""The declarative base names every constraint kind."""

from app.db.base import Base


def test_naming_convention_covers_every_constraint_kind() -> None:
    assert set(Base.metadata.naming_convention) >= {"ix", "uq", "ck", "fk", "pk"}
