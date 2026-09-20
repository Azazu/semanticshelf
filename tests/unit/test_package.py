"""Smoke test: the package is installed and its version constant matches the distribution.

It fails when the project is not installed (import or metadata error), when
`app.__version__` drifts from `pyproject.toml`, or when pytest does not see the
package — three real regressions of the tooling this change sets up.
"""

from importlib.metadata import version

import app


def test_version_matches_distribution() -> None:
    assert app.__version__ == version("semanticshelf")
