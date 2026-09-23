"""The four pages, rendered against a service that answers from memory.

`AppTest` runs a page module in-process, so these are the real pages — the same
file `streamlit run` executes — and the only thing replaced is what they talk
to.

What is asserted is what a person would *see* after a click, not what the page
asked for. Gate 2 found seven defects behind that difference: a page can send
exactly the right request and still show the wrong thing, because Streamlit
draws the page and only then runs the code that changes it.
"""

from pathlib import Path

import httpx
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from tests.ui.conftest import Service, asset, page_of, problem
from ui import shell

pytestmark = pytest.mark.ui

PAGES = Path(__file__).resolve().parents[2] / "ui" / "pages"


def run(page: str) -> AppTest:
    test = AppTest.from_file(str(PAGES / page), default_timeout=30)
    return test.run()


def captions_of(test: AppTest) -> list[str]:
    """What each picture is labelled with — the caption belongs to the image."""
    return [str(picture.caption) for element in test.image for picture in element.proto.imgs]


def pictures(test: AppTest) -> int:
    return sum(len(element.proto.imgs) for element in test.image)


def messages(test: AppTest) -> str:
    """Everything the page said, in one string to look for wording in."""
    parts = [element.value for element in test.error] + [element.value for element in test.info]
    parts += [element.value for element in test.warning]
    parts += [element.value for element in test.success]
    parts += [element.value for element in test.markdown]
    return " ".join(str(part) for part in parts)


def button(test: AppTest, label: str) -> object:
    found = [candidate for candidate in test.button if candidate.label == label]
    assert found, f"no {label!r} button on the page"
    return found[0]


def searching(service: Service, pages: list[dict[str, object]]) -> None:
    """Answer each search with the page matching its offset."""

    def handler(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params.get("offset", 0))
        return httpx.Response(200, json=pages[offset // 12])

    service.on("/api/v1/search/text", handler)


def found(
    items: list[dict[str, object]],
    *,
    has_more: bool = False,
    model: str = "clip-vit-l14",
    truncated: bool = False,
) -> dict[str, object]:
    return {
        "items": items,
        "limit": 12,
        "offset": 0,
        "has_more": has_more,
        "model": model,
        "query_truncated": truncated,
    }


def hit(identifier: str, score: float = 0.31, **kwargs: object) -> dict[str, object]:
    return {"score": score, "asset": asset(identifier, **kwargs)}  # type: ignore[arg-type]


# --- search ---------------------------------------------------------------------


def test_search_shows_what_was_found_with_its_score_and_the_model(searched: Service) -> None:
    test = run("search.py")

    test.text_input[0].set_value("a blue circle").run()
    button(test, "Search").click().run()

    assert "clip-vit-l14" in messages(test)
    assert pictures(test) == 1
    assert any("0.310" in caption for caption in captions_of(test))
    assert searched.queries("/api/v1/search/text")[0]["q"] == "a blue circle"


def test_search_says_when_nothing_matched(service: Service) -> None:
    service.answer("/api/v1/search/text", found([]))
    test = run("search.py")

    test.text_input[0].set_value("nothing like this").run()
    button(test, "Search").click().run()

    assert "Nothing matched" in messages(test)


def test_more_shows_the_next_page_immediately(service: Service) -> None:
    """One click, and the new pictures are on the screen — not after some other
    interaction happens to redraw the page."""
    searching(service, [found([hit("1")], has_more=True), found([hit("2")], has_more=False)])
    test = run("search.py")
    test.text_input[0].set_value("dragon").run()
    button(test, "Search").click().run()
    assert pictures(test) == 1

    button(test, "More").click().run()

    assert pictures(test) == 2, "both pages are shown after one click"
    assert [query["offset"] for query in service.queries("/api/v1/search/text")] == ["0", "12"]
    assert not [candidate for candidate in test.button if candidate.label == "More"], (
        "the last page offers no more"
    )


def test_more_over_a_page_that_repeats_an_asset_still_renders(service: Service) -> None:
    """The service may hand back an asset that is already on screen — a group of
    identical scores straddling a page edge is not promised to be cut the same
    way twice — and until Gate 2 that made the page stop rendering altogether:
    two thumbnails claimed one widget key.
    """
    searching(
        service,
        [found([hit("1"), hit("2")], has_more=True), found([hit("2"), hit("3")], has_more=False)],
    )
    test = run("search.py")
    test.text_input[0].set_value("dragon").run()
    button(test, "Search").click().run()

    button(test, "More").click().run()

    assert not test.exception, [str(error.value) for error in test.exception]
    assert pictures(test) == 3, "the repeat is shown once, and the new one is shown"
    assert [query["offset"] for query in service.queries("/api/v1/search/text")] == ["0", "12"], (
        "and the offset is still the service's place in the ranking"
    )


def test_the_action_after_such_a_page_still_names_its_own_asset(
    service: Service, monkeypatch: pytest.MonkeyPatch
) -> None:
    switched: list[str] = []
    monkeypatch.setattr(st, "switch_page", lambda page: switched.append(str(page)))
    searching(
        service,
        [found([hit("1"), hit("2")], has_more=True), found([hit("2"), hit("3")], has_more=False)],
    )
    test = run("search.py")
    test.text_input[0].set_value("dragon").run()
    button(test, "Search").click().run()
    button(test, "More").click().run()

    actions = [candidate for candidate in test.button if candidate.label == shell.SIMILAR_LABEL]
    assert len(actions) == 3
    actions[2].click().run()

    assert test.session_state[shell.SIMILAR_ASKED] == "3"
    assert switched == [shell.SIMILAR_PAGE]


def test_a_refused_search_keeps_the_results_that_were_there(service: Service) -> None:
    """A refusal costs the refused request, not what a person already had."""
    service.answer("/api/v1/search/text", found([hit("1")]))
    test = run("search.py")
    test.text_input[0].set_value("dragon").run()
    button(test, "Search").click().run()
    assert pictures(test) == 1

    service.on(
        "/api/v1/search/text",
        lambda request: problem(422, "Unprocessable Entity", "q must not be empty"),
    )
    test.text_input[0].set_value("   x").run()
    button(test, "Search").click().run()

    assert "q must not be empty" in messages(test)
    assert pictures(test) == 1, "the previous results are still there"
    assert not test.exception


def test_more_repeats_the_search_that_produced_the_results(service: Service) -> None:
    """Editing the box without searching cannot mix two rankings: paging uses
    what was asked, not what is typed."""
    searching(service, [found([hit("1")], has_more=True), found([hit("2")])])
    test = run("search.py")
    test.text_input[0].set_value("cat").run()
    button(test, "Search").click().run()

    test.text_input[0].set_value("dog").run()  # typed, not searched
    button(test, "More").click().run()

    asked = service.queries("/api/v1/search/text")
    assert [query["q"] for query in asked] == ["cat", "cat"], (
        "the second page is of the same search"
    )


def test_more_is_offered_even_when_a_tag_emptied_the_page(service: Service) -> None:
    """The tag filters what was fetched; a page it empties is not the end of the
    ranking, and the way to the rest must stay on the screen."""
    searching(
        service,
        [
            found([hit("1", tags=["cat"])], has_more=True),
            found([hit("2", tags=["dog"])], has_more=False),
        ],
    )
    test = run("search.py")
    test.text_input[0].set_value("animal").run()
    test.text_input[1].set_value("dog").run()
    button(test, "Search").click().run()

    assert pictures(test) == 0
    assert "dog" in messages(test)

    button(test, "More").click().run()

    assert pictures(test) == 1, "the match on the next page is reachable"


def test_search_says_when_the_query_was_cut(service: Service) -> None:
    service.answer("/api/v1/search/text", found([], truncated=True))
    test = run("search.py")

    test.text_input[0].set_value("d" * 200).run()
    button(test, "Search").click().run()

    assert "could not take the whole query" in messages(test)


# --- browse ----------------------------------------------------------------------


def browsing(
    service: Service, pages: dict[int, dict[str, object]], *, by_tag: dict | None = None
) -> None:
    """Answer the listing from a page per offset, and per tag when asked."""

    def handler(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params.get("offset", 0))
        tag = request.url.params.get("tags_all")
        if tag and by_tag is not None:
            return httpx.Response(200, json=by_tag.get(offset, page_of([])))
        return httpx.Response(200, json=pages.get(offset, page_of([])))

    service.on("/api/v1/assets", handler)


def test_browse_shows_the_store_and_the_tags_in_use(service: Service) -> None:
    service.answer("/api/v1/tags", {"items": [{"tag": "demo", "assets": 2}], "limit": 50})
    browsing(service, {0: page_of([asset("1"), asset("2")])})

    test = run("browse.py")

    assert "Showing 2" in messages(test)
    assert "demo (2)" in [str(option) for option in test.selectbox[0].options]


def test_browse_narrows_by_the_tag_that_was_picked(service: Service) -> None:
    service.answer("/api/v1/tags", {"items": [{"tag": "demo", "assets": 1}], "limit": 50})
    browsing(service, {0: page_of([asset("1"), asset("2")])}, by_tag={0: page_of([asset("1")])})
    test = run("browse.py")

    test.selectbox[0].set_value("demo (1)").run()

    assert service.queries("/api/v1/assets")[-1]["tags_all"] == "demo"
    assert pictures(test) == 1, "the narrowed page is what is shown"


def test_a_tag_picked_on_a_later_page_starts_that_tag_at_its_first_page(
    service: Service,
) -> None:
    """The defect Gate 2 named: narrowing while deep in the listing asked for
    the tag at an offset it has no items at, and stranded the person there."""
    service.answer("/api/v1/tags", {"items": [{"tag": "demo", "assets": 1}], "limit": 50})
    browsing(
        service,
        {0: page_of([asset("1")], has_more=True), 12: page_of([asset("2")])},
        by_tag={0: page_of([asset("9")])},
    )
    test = run("browse.py")
    button(test, "Next page").click().run()
    assert service.queries("/api/v1/assets")[-1]["offset"] == "12"

    test.selectbox[0].set_value("demo (1)").run()

    assert service.queries("/api/v1/assets")[-1] == {
        "limit": "12",
        "offset": "0",
        "tags_all": "demo",
    }
    assert pictures(test) == 1


def test_browse_pages_forward_and_back(service: Service) -> None:
    service.answer("/api/v1/tags", {"items": [], "limit": 50})
    browsing(service, {0: page_of([asset("1")], has_more=True), 12: page_of([asset("2")])})
    test = run("browse.py")

    button(test, "Next page").click().run()

    assert "from 13" in messages(test)
    assert captions_of(test) == ["picture.png"]

    button(test, "Previous page").click().run()

    assert "from 1" in messages(test)


def test_browse_opens_one_picture_with_everything_known_about_it(service: Service) -> None:
    service.answer("/api/v1/tags", {"items": [], "limit": 50})
    browsing(service, {0: page_of([asset("1")])})
    service.answer("/api/v1/assets/1", asset("1", meta={"dataset": "coco-val2017"}))
    test = run("browse.py")

    test.selectbox[1].set_value("1").run()

    assert "/api/v1/assets/1" in service.paths()
    assert test.json, "the metadata is shown"


def test_browse_deletes_only_after_a_confirmation_and_then_shows_it_is_gone(
    service: Service,
) -> None:
    service.answer("/api/v1/tags", {"items": [], "limit": 50})
    listing = {0: page_of([asset("1"), asset("2")])}
    browsing(service, listing)

    def one_asset(request: httpx.Request) -> httpx.Response:
        if request.method == "DELETE":
            listing[0] = page_of([asset("2")])  # the store, after the deletion
            return httpx.Response(204)
        return httpx.Response(200, json=asset("1"))

    service.on("/api/v1/assets/1", one_asset)
    test = run("browse.py")
    test.selectbox[1].set_value("1").run()
    assert not [request for request in service.asked if request.method == "DELETE"]

    test.checkbox[0].check().run()
    button(test, "Delete").click().run()

    assert [r.method for r in service.asked if r.method == "DELETE"] == ["DELETE"]
    assert "Deleted" in messages(test)
    assert pictures(test) == 1, "the deleted picture is gone from the grid at once"
    assert not test.json, "and so is its detail"
    assert not test.checkbox, "the confirmation is not left ticked for the next one"


def test_browse_says_when_the_store_is_empty(service: Service) -> None:
    service.answer("/api/v1/tags", {"items": [], "limit": 50})
    browsing(service, {0: page_of([])})

    test = run("browse.py")

    assert "make demo" in messages(test)


# --- upload ----------------------------------------------------------------------


class Chosen:
    """What `st.file_uploader` hands a page once a person has picked a file."""

    name = "rose.png"
    type = "image/png"

    def getvalue(self) -> bytes:
        return b"pretend png"


def with_a_file_chosen(monkeypatch: pytest.MonkeyPatch) -> None:
    """AppTest cannot drive a file uploader, so the widget is replaced with one
    that has already been used. Everything after it is the page's own path."""
    import streamlit as st

    monkeypatch.setattr(st, "file_uploader", lambda *args, **kwargs: Chosen())


def test_upload_shows_what_the_service_stored(
    service: Service, monkeypatch: pytest.MonkeyPatch
) -> None:
    service.answer("/api/v1/assets", asset("9", name="rose.png"), status=201)
    with_a_file_chosen(monkeypatch)
    test = run("upload.py")

    test.text_input[0].set_value("garden,flower").run()
    button(test, "Upload").click().run()

    assert "Stored as 9" in messages(test)
    assert service.asked[-1].method == "POST"
    assert "garden,flower" in service.asked[-1].content.decode("latin-1")
    assert not test.exception


def test_upload_shows_a_refusal_as_the_service_worded_it(
    service: Service, monkeypatch: pytest.MonkeyPatch
) -> None:
    service.on(
        "/api/v1/assets",
        lambda request: problem(415, "Unsupported Media Type", "detected application/pdf"),
    )
    with_a_file_chosen(monkeypatch)
    test = run("upload.py")

    button(test, "Upload").click().run()

    assert "Unsupported Media Type" in messages(test)
    assert "detected application/pdf" in messages(test)
    assert not test.exception, "a refusal is not a crash"


def test_upload_asks_for_nothing_until_a_file_is_chosen(service: Service) -> None:
    test = run("upload.py")

    assert test.button[0].disabled
    assert service.asked == []


# --- status ----------------------------------------------------------------------


def test_status_shows_readiness_and_the_counters(service: Service) -> None:
    service.answer("/ready", {"status": "ready", "checks": {"database": "ok", "media": "ok"}})
    service.answer(
        "/api/v1/stats",
        {
            "assets": 20,
            "stored_bytes": 3_403_692,
            "work": [{"model": "clip-vit-l14", "status": "done", "jobs": 20}],
            "oldest_waiting_seconds": None,
        },
    )

    test = run("status.py")

    assert "ready" in messages(test)
    assert "Nothing is waiting" in messages(test)
    assert test.metric[0].value == "20"


def test_status_shows_each_failed_check_when_the_service_is_not_ready(service: Service) -> None:
    service.on(
        "/ready",
        lambda request: problem(
            503,
            "Service Unavailable",
            "not ready",
            checks={"database": "OperationalError", "media": "ok"},
        ),
    )
    service.answer(
        "/api/v1/stats",
        {"assets": 0, "stored_bytes": 0, "work": [], "oldest_waiting_seconds": None},
    )

    test = run("status.py")

    assert "not ready" in messages(test)
    assert not test.exception
    assert any("OperationalError" in str(cell) for cell in test.table[0].value.values.ravel())


def test_status_says_how_long_the_oldest_work_has_waited(service: Service) -> None:
    service.answer("/ready", {"status": "ready", "checks": {"database": "ok"}})
    service.answer(
        "/api/v1/stats",
        {
            "assets": 5,
            "stored_bytes": 10,
            "work": [{"model": "m", "status": "pending", "jobs": 1}],
            "oldest_waiting_seconds": 3600.4,
        },
    )

    test = run("status.py")

    assert "3600 seconds" in messages(test)


def test_a_page_whose_service_is_down_still_renders(service: Service) -> None:
    """Nothing is stubbed, so every call is refused — and every page survives."""
    for page in ("search.py", "browse.py", "upload.py", "status.py"):
        test = run(page)

        assert not test.exception, page
        assert test.title, f"{page} still drew itself"
