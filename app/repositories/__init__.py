"""Persistence, one repository per table.

A repository is the only place that knows SQLAlchemy. It takes a session, it
returns the frozen objects of `app.domain`, and it never hands an ORM instance
outwards: a closed session must not be able to turn a field access into a query.
"""

from app.repositories.assets import AssetRepository
from app.repositories.embeddings import EmbeddingRepository
from app.repositories.jobs import IndexingJobRepository

__all__ = ["AssetRepository", "EmbeddingRepository", "IndexingJobRepository"]
