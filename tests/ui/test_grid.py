"""The grid every page draws its pictures with.

It is shared, so it is tested apart from the pages: what a page hands it is a
page's business, but a component that stops rendering on input nobody promised
not to give it takes the whole screen down with it — which is what Gate 2 found
when the action under each thumbnail was keyed by the asset alone.
"""

from typing import Any

import pytest
from streamlit.testing.v1 import AppTest

from tests.ui.conftest import Service, asset
from ui import shell

pytestmark = pytest.mark.ui


def grid_of(identifiers: list[str]) -> None:
    """A tiny app: one grid, over exactly these assets."""
    import streamlit as st

    from tests.ui.conftest import asset as make_asset
    from ui.shell import thumbnails

    clicked: list[str] = []
    st.session_state.setdefault("clicked", clicked)
    thumbnails(
        [make_asset(identifier) for identifier in identifiers],
        on_similar=lambda asset_id: st.session_state["clicked"].append(asset_id),
    )


def test_a_list_that_holds_one_asset_twice_still_renders(service: Service) -> None:
    test = AppTest.from_function(
        grid_of, args=((["11111111", "11111111"],)), default_timeout=30
    ).run()

    assert not test.exception, [str(error.value) for error in test.exception]
    assert len([picture for element in test.image for picture in element.proto.imgs]) == 2
    assert len([b for b in test.button if b.label == shell.SIMILAR_LABEL]) == 2


def test_each_action_still_names_its_own_asset(service: Service) -> None:
    test = AppTest.from_function(
        grid_of, args=((["11111111", "22222222", "33333333"],)), default_timeout=30
    ).run()

    actions = [b for b in test.button if b.label == shell.SIMILAR_LABEL]
    actions[1].click().run()

    assert test.session_state["clicked"] == ["22222222"]


# --- the helper the pages accumulate with -------------------------------------


def hit(identifier: str) -> dict[str, Any]:
    return {"score": 0.3, "asset": asset(identifier)}


def ids(items: list[Any]) -> list[str]:
    return [shell.asset_of(item)["id"] for item in items]


def test_a_page_with_nothing_new_adds_nothing() -> None:
    shown = [hit("1"), hit("2")]

    assert ids(shell.without_repeats(shown, [hit("2")])) == ["1", "2"]


def test_the_new_part_of_a_page_is_kept_in_order() -> None:
    shown = [hit("1")]

    assert ids(shell.without_repeats(shown, [hit("1"), hit("2"), hit("3")])) == ["1", "2", "3"]


def test_a_page_that_repeats_itself_is_kept_once() -> None:
    assert ids(shell.without_repeats([], [hit("1"), hit("1")])) == ["1"]


def test_it_works_on_assets_as_well_as_on_hits() -> None:
    """Browse hands the grid assets, Search hands it hits; the helper must not
    care which, because the grid does not."""
    assert ids(shell.without_repeats([asset("1")], [asset("1"), asset("2")])) == ["1", "2"]
