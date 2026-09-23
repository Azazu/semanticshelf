"""What every page shares: a client, an error surface, and a grid of pictures.

A page shows a refusal the way the service worded it and then goes on being a
page — never a traceback, never a bare status code.
"""

from collections.abc import Callable, Mapping, Sequence
from typing import Any

import streamlit as st

from ui.client import Client, ServiceError, address_of, client

#: How many pictures a row of the grid holds.
COLUMNS = 4

#: The page that answers "what looks like this one", and the state key it reads
#: to know which asset was asked about.
SIMILAR_PAGE = "pages/similar.py"
SIMILAR_ASKED = "similar_pending"
SIMILAR_LABEL = "Find similar"


def service() -> Client:
    """The client this page run uses. A test replaces it with its own."""
    return client()


def refused(error: ServiceError) -> None:
    """Show what the service said, and let the person carry on."""
    st.error(f"**{error.title}** — {error.detail}")
    checks = error.body.get("checks")
    if isinstance(checks, Mapping):
        st.table({"check": list(checks), "outcome": [str(value) for value in checks.values()]})


def open_similar(asset_id: str) -> None:
    """Remember which asset was asked about, and go to the page that answers.

    The state is written *before* the switch, because the page it switches to
    runs from the top and reads it: a click that navigated first and remembered
    afterwards would arrive at an empty page.
    """
    st.session_state[SIMILAR_ASKED] = asset_id
    st.switch_page(SIMILAR_PAGE)


def thumbnails(
    items: Sequence[Mapping[str, Any]],
    *,
    captions: Sequence[str] | None = None,
    on_similar: Callable[[str], None] | None = open_similar,
) -> None:
    """A grid of pictures, each fetched by the browser from the service.

    The caption belongs to the picture rather than to the cell under it, so a
    row of pictures with different shapes still reads as a row.

    Every picture carries the one action that starts from a picture rather than
    from words. `on_similar` is how the page that already answers that question
    keeps it from navigating to itself; `None` leaves the action off entirely.
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
                if on_similar is not None and st.button(
                    SIMILAR_LABEL, key=f"similar-{asset['id']}", width="stretch"
                ):
                    on_similar(asset["id"])


def asset_caption(item: Mapping[str, Any]) -> str:
    """One line under a search result: its score and what it is called."""
    asset = item["asset"]
    return f"{item['score']:.3f} · {asset['original_filename'] or asset['id'][:8]}"
