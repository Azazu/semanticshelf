"""SQLAlchemy mappings. Importing this package populates `Base.metadata`, which
is what `alembic/env.py` compares against; nothing outside the repositories may
import these classes.
"""

from app.models.asset import Asset
from app.models.embedding import Embedding
from app.models.indexing_job import IndexingJob

__all__ = ["Asset", "Embedding", "IndexingJob"]
