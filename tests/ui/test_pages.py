"""The four pages, rendered against a service that answers from memory.

`AppTest` runs a page module in-process, so these are the real pages — the same
file `streamlit run` executes — and the only thing replaced is what they talk
to.
"""

from pathlib import Path

import httpx
import pytest
from streamlit.testing.v1 import AppTest

from tests.ui.conftest import Service, asset, page_of, problem

pytestmark = pytest.mark.ui

PAGES = Path(__file__).resolve().parents[2] / "ui" / "pages"


def run(page: str) -> AppTest:
    test = AppTest.from_file(str(PAGES / page), default_timeout=30)
    return test.run()


def captions_of(test: AppTest) -> list[str]:
    """What each picture is labelled with — the caption belongs to the image."""
    return [str(picture.caption) for element in test.image for picture in element.proto.imgs]


def messages(test: AppTest) -> str:
    """Everything the page said, in one string to look for wording in."""
    parts = [element.value for element in test.error] + [element.value for element in test.info]
    parts += [element.value for element in test.warning] + [
        element.value for element in test.success
    ]
    parts += [element.value for element in test.markdown]
    parts += [element.value for element in test.caption] if hasattr(test, "caption") else []
    return " ".join(str(part) for part in parts)


# --- search ---------------------------------------------------------------------


def test_search_shows_what_was_found_with_its_score_and_the_model(searched: Service) -> None:
    test = run("search.py")

    test.text_input[0].set_value("a blue circle").run()
    test.button[0].click().run()

    assert "clip-vit-l14" in messages(test)
    assert test.image, "the picture that was found is shown"
    assert any("0.310" in str(caption) for caption in captions_of(test)), "with its score"
    assert searched.queries("/api/v1/search/text")[0]["q"] == "a blue circle"


def test_search_says_when_nothing_matched(service: Service) -> None:
    service.answer(
        "/api/v1/search/text",
        {
            "items": [],
            "limit": 12,
            "offset": 0,
            "has_more": False,
            "model": "clip-vit-l14",
            "query_truncated": False,
        },
    )
    test = run("search.py")

    test.text_input[0].set_value("nothing like this").run()
    test.button[0].click().run()

    assert "Nothing matched" in messages(test)


def test_search_asks_for_the_next_offset_when_more_is_pressed(service: Service) -> None:
    service.answer(
        "/api/v1/search/text",
        {
            "items": [{"score": 0.5, "asset": asset("1")}],
            "limit": 12,
            "offset": 0,
            "has_more": True,
            "model": "clip-vit-l14",
            "query_truncated": False,
        },
    )
    test = run("search.py")
    test.text_input[0].set_value("dragon").run()
    test.button[0].click().run()

    more = [button for button in test.button if button.label == "More"]
    assert more, "a page with more results offers to fetch them"
    more[0].click().run()

    assert [query["offset"] for query in service.queries("/api/v1/search/text")] == ["0", "12"]


def test_search_shows_a_refusal_as_the_service_worded_it(service: Service) -> None:
    service.on(
        "/api/v1/search/text",
        lambda request: problem(422, "Unprocessable Entity", "q must not be empty"),
    )
    test = run("search.py")

    test.text_input[0].set_value("   ").run()
    test.button[0].click().run()

    assert "q must not be empty" in messages(test)
    assert not test.exception, "a refusal is not a crash"


def test_search_says_when_the_query_was_cut(service: Service) -> None:
    service.answer(
        "/api/v1/search/text",
        {
            "items": [],
            "limit": 12,
            "offset": 0,
            "has_more": False,
            "model": "clip-vit-l14",
            "query_truncated": True,
        },
    )
    test = run("search.py")

    test.text_input[0].set_value("d" * 200).run()
    test.button[0].click().run()

    assert "could not take the whole query" in messages(test)


# --- browse ----------------------------------------------------------------------


def test_browse_shows_the_store_and_the_tags_in_use(service: Service) -> None:
    service.answer("/api/v1/tags", {"items": [{"tag": "demo", "assets": 2}], "limit": 50})
    service.answer("/api/v1/assets", page_of([asset("1"), asset("2")]))

    test = run("browse.py")

    assert "Showing 2" in messages(test)
    assert "demo (2)" in [str(option) for option in test.selectbox[0].options]


def test_browse_narrows_by_the_tag_that_was_picked(service: Service) -> None:
    service.answer("/api/v1/tags", {"items": [{"tag": "demo", "assets": 2}], "limit": 50})
    service.answer("/api/v1/assets", page_of([asset("1")]))
    test = run("browse.py")

    test.selectbox[0].set_value("demo (2)").run()

    assert service.queries("/api/v1/assets")[-1]["tags_all"] == "demo"


def test_browse_opens_one_picture_with_everything_known_about_it(service: Service) -> None:
    service.answer("/api/v1/tags", {"items": [], "limit": 50})
    service.answer("/api/v1/assets", page_of([asset("1")]))
    service.answer("/api/v1/assets/1", asset("1", meta={"dataset": "coco-val2017"}))
    test = run("browse.py")

    test.selectbox[1].set_value("1").run()

    assert "/api/v1/assets/1" in service.paths()
    assert test.json, "the metadata is shown"


def test_browse_deletes_only_after_a_confirmation(service: Service) -> None:
    service.answer("/api/v1/tags", {"items": [], "limit": 50})
    service.answer("/api/v1/assets", page_of([asset("1")]))
    service.answer("/api/v1/assets/1", asset("1"))
    service.on(
        "/api/v1/assets/1",
        lambda request: (
            httpx.Response(204)
            if request.method == "DELETE"
            else httpx.Response(200, json=asset("1"))
        ),
    )
    test = run("browse.py")
    test.selectbox[1].set_value("1").run()

    assert not [request for request in service.asked if request.method == "DELETE"]

    test.checkbox[0].check().run()
    [button for button in test.button if button.label == "Delete"][0].click().run()

    assert [request.method for request in service.asked if request.method == "DELETE"] == ["DELETE"]
    assert "Deleted" in messages(test)


def test_browse_says_when_the_store_is_empty(service: Service) -> None:
    service.answer("/api/v1/tags", {"items": [], "limit": 50})
    service.answer("/api/v1/assets", page_of([]))

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
    [button for button in test.button if button.label == "Upload"][0].click().run()

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

    [button for button in test.button if button.label == "Upload"][0].click().run()

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
