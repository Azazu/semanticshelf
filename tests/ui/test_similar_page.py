"""The fifth page, and the action that reaches it from every other one.

Like the rest of the interface's suite, what is asserted is what a person would
*see* after a click rather than what was sent: a page can send exactly the right
request and still show the wrong thing, because Streamlit draws the page and
only then runs the code that changes it.
"""

import io
from pathlib import Path
from typing import Any

import httpx
import pytest
import streamlit as st
from PIL import Image
from streamlit.testing.v1 import AppTest

from tests.ui.conftest import Service, asset, problem
from ui import shell

pytestmark = pytest.mark.ui

PAGES = Path(__file__).resolve().parents[2] / "ui" / "pages"
SIMILAR = "/api/v1/assets/{id}/similar"
IMAGE_SEARCH = "/api/v1/search/image"


def run(page: str) -> AppTest:
    test = AppTest.from_file(str(PAGES / page), default_timeout=30)
    return test.run()


def pictures(test: AppTest) -> int:
    return sum(len(element.proto.imgs) for element in test.image)


def captions_of(test: AppTest) -> list[str]:
    return [str(picture.caption) for element in test.image for picture in element.proto.imgs]


def messages(test: AppTest) -> str:
    parts = [element.value for element in test.error] + [element.value for element in test.info]
    parts += [element.value for element in test.warning]
    parts += [element.value for element in test.markdown]
    return " ".join(str(part) for part in parts)


def button(test: AppTest, label: str) -> Any:
    found = [candidate for candidate in test.button if candidate.label == label]
    assert found, f"no {label!r} button on the page: {[b.label for b in test.button]}"
    return found[0]


def neighbours(items: list[dict[str, Any]], *, has_more: bool = False) -> dict[str, Any]:
    return {
        "items": items,
        "limit": 12,
        "offset": 0,
        "has_more": has_more,
        "model": "dinov2-large",
        "query_truncated": False,
    }


def hit(identifier: str, score: float = 0.87, **kwargs: Any) -> dict[str, Any]:
    return {"score": score, "asset": asset(identifier, **kwargs)}


def picture_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (32, 32), color=(10, 120, 200)).save(buffer, format="PNG")
    return buffer.getvalue()


# --- a picture uploaded here ---------------------------------------------------


def test_a_picture_finds_what_looks_like_it(service: Service) -> None:
    service.answer(IMAGE_SEARCH, neighbours([hit("11111111", name="blue.png")]))
    test = run("similar.py")

    test.file_uploader[0].set_value(("query.png", picture_bytes(), "image/png")).run()
    button(test, "Search by picture").click().run()

    assert pictures(test) == 1
    assert any("0.870" in caption for caption in captions_of(test))
    assert "dinov2-large" in messages(test)
    assert "was not stored" in messages(test)
    assert service.paths().count(IMAGE_SEARCH) == 1


def test_asking_without_a_picture_says_so_and_asks_nothing(service: Service) -> None:
    test = run("similar.py")

    button(test, "Search by picture").click().run()

    assert "Choose a picture first" in messages(test)
    assert service.paths() == []


def test_a_refused_picture_is_shown_in_the_services_own_words(service: Service) -> None:
    """A name is not a format: the uploader only keeps out the extensions the
    service cannot store, and what a file *is* is still decided by the service
    from its bytes."""
    service.on(
        IMAGE_SEARCH,
        lambda request: problem(
            415, "Unsupported Media Type", "the file does not decode as an image"
        ),
    )
    test = run("similar.py")

    test.file_uploader[0].set_value(("lying.png", b"not a picture at all", "image/png")).run()
    button(test, "Search by picture").click().run()

    assert "Unsupported Media Type" in messages(test)
    assert "does not decode as an image" in messages(test)
    assert pictures(test) == 0


def test_more_shows_the_next_page_of_neighbours_immediately(service: Service) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        offset = int(request.content.count(b"offset") and _offset_of(request))
        body = neighbours([hit("2")]) if offset else neighbours([hit("1")], has_more=True)
        return httpx.Response(200, json=body)

    service.on(IMAGE_SEARCH, handler)
    test = run("similar.py")
    test.file_uploader[0].set_value(("query.png", picture_bytes(), "image/png")).run()
    button(test, "Search by picture").click().run()
    assert pictures(test) == 1

    button(test, "More").click().run()

    assert pictures(test) == 2, "both pages are shown after one click"
    assert not [candidate for candidate in test.button if candidate.label == "More"]


def _offset_of(request: httpx.Request) -> int:
    """The `offset` form field of a multipart body, without parsing it whole."""
    marker = b'name="offset"\r\n\r\n'
    body = request.content
    index = body.find(marker)
    if index < 0:
        return 0
    return int(body[index + len(marker) :].split(b"\r\n", 1)[0])


# --- a picture the store already holds -----------------------------------------


def test_an_asset_that_arrived_from_another_page_is_answered_at_once(service: Service) -> None:
    """The action sets the state and switches; the page must answer in the run
    it arrives in, not one interaction later."""
    service.answer(SIMILAR.format(id="22222222"), neighbours([hit("33333333")]))
    test = AppTest.from_file(str(PAGES / "similar.py"), default_timeout=30)
    test.session_state[shell.SIMILAR_ASKED] = "22222222"

    test.run()

    assert pictures(test) == 1
    assert "22222222"[:8] in messages(test)
    assert "not among its own neighbours" in messages(test)
    assert service.paths() == [SIMILAR.format(id="22222222")]


def test_an_asset_with_no_vector_yet_is_shown_as_the_service_put_it(service: Service) -> None:
    service.on(
        SIMILAR.format(id="22222222"),
        lambda request: problem(409, "Conflict", "asset 22222222 has no 'dinov2-large' vector yet"),
    )
    test = AppTest.from_file(str(PAGES / "similar.py"), default_timeout=30)
    test.session_state[shell.SIMILAR_ASKED] = "22222222"

    test.run()

    assert "Conflict" in messages(test)
    assert "no 'dinov2-large' vector yet" in messages(test)
    assert pictures(test) == 0


def test_a_neighbour_can_be_asked_about_without_leaving_the_page(service: Service) -> None:
    service.answer(SIMILAR.format(id="22222222"), neighbours([hit("33333333")]))
    service.answer(SIMILAR.format(id="33333333"), neighbours([hit("44444444")]))
    test = AppTest.from_file(str(PAGES / "similar.py"), default_timeout=30)
    test.session_state[shell.SIMILAR_ASKED] = "22222222"
    test.run()

    button(test, shell.SIMILAR_LABEL).click().run()

    assert "33333333"[:8] in messages(test), "the question is now about the neighbour"
    assert service.paths() == [
        SIMILAR.format(id="22222222"),
        SIMILAR.format(id="33333333"),
    ], "and it was asked directly, without navigating away and back"


def test_an_empty_answer_says_what_might_be_missing(service: Service) -> None:
    service.answer(SIMILAR.format(id="22222222"), neighbours([]))
    test = AppTest.from_file(str(PAGES / "similar.py"), default_timeout=30)
    test.session_state[shell.SIMILAR_ASKED] = "22222222"

    test.run()

    assert "index missing" in messages(test), "the command that fills the vectors in"


# --- the action under every thumbnail ------------------------------------------


def test_the_action_is_under_every_picture_the_search_page_shows(
    service: Service, monkeypatch: pytest.MonkeyPatch
) -> None:
    switched: list[str] = []
    monkeypatch.setattr(st, "switch_page", lambda page: switched.append(str(page)))
    service.answer(
        "/api/v1/search/text",
        {
            "items": [hit("11111111"), hit("22222222")],
            "limit": 12,
            "offset": 0,
            "has_more": False,
            "model": "clip-vit-l14",
            "query_truncated": False,
        },
    )
    test = run("search.py")
    test.text_input[0].set_value("a dragon").run()
    button(test, "Search").click().run()

    actions = [candidate for candidate in test.button if candidate.label == shell.SIMILAR_LABEL]

    assert len(actions) == 2, "one under each result"
    actions[1].click().run()

    assert test.session_state[shell.SIMILAR_ASKED] == "22222222"
    assert switched == [shell.SIMILAR_PAGE], "and it went to the page that answers"


def test_the_action_is_under_every_picture_the_browse_page_shows(
    service: Service, monkeypatch: pytest.MonkeyPatch
) -> None:
    switched: list[str] = []
    monkeypatch.setattr(st, "switch_page", lambda page: switched.append(str(page)))
    service.answer("/api/v1/tags", {"items": []})
    service.answer(
        "/api/v1/assets",
        {"items": [asset("11111111")], "limit": 12, "offset": 0, "has_more": False},
    )
    test = run("browse.py")

    actions = [candidate for candidate in test.button if candidate.label == shell.SIMILAR_LABEL]
    assert len(actions) == 1

    actions[0].click().run()

    assert test.session_state[shell.SIMILAR_ASKED] == "11111111"
    assert switched == [shell.SIMILAR_PAGE]
