"""What every page shares: a client, an error surface, and a grid of pictures.

A page shows a refusal the way the service worded it and then goes on being a
page — never a traceback, never a bare status code.
"""

from collections.abc import Mapping, Sequence
from typing import Any

import streamlit as st

from ui.client import Client, ServiceError, address_of, client

#: How many pictures a row of the grid holds.
COLUMNS = 4


def service() -> Client:
    """The client this page run uses. A test replaces it with its own."""
    return client()


def refused(error: ServiceError) -> None:
    """Show what the service said, and let the person carry on."""
    st.error(f"**{error.title}** — {error.detail}")
    checks = error.body.get("checks")
    if isinstance(checks, Mapping):
        st.table({"check": list(checks), "outcome": [str(value) for value in checks.values()]})


def thumbnails(
    items: Sequence[Mapping[str, Any]], *, captions: Sequence[str] | None = None
) -> None:
    """A grid of pictures, each fetched by the browser from the service.

    The caption belongs to the picture rather than to the cell under it, so a
    row of pictures with different shapes still reads as a row.
    """
    for row in range(0, len(items), COLUMNS):
        cells = st.columns(COLUMNS)
        for offset, item in enumerate(items[row : row + COLUMNS]):
            asset = item["asset"] if "asset" in item else item
            caption = captions[row + offset] if captions else asset["original_filename"]
            with cells[offset]:
                st.image(
                    address_of(asset["links"]["thumbnail"]),
                    caption=caption or asset["id"][:8],
                    width="stretch",
                )


def asset_caption(item: Mapping[str, Any]) -> str:
    """One line under a search result: its score and what it is called."""
    asset = item["asset"]
    return f"{item['score']:.3f} · {asset['original_filename'] or asset['id'][:8]}"
