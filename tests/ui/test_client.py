"""The one module that speaks HTTP: what it asks for, and how a refusal reads."""

import httpx
import pytest

from tests.ui.conftest import Service, asset, problem
from ui import client as client_module
from ui.client import ServiceError, address_of

pytestmark = pytest.mark.ui


def test_every_call_goes_to_the_service_it_was_told_about(service: Service) -> None:
    service.answer("/api/v1/stats", {"assets": 0})

    client_module.client().stats()

    assert service.asked[0].url.host == "service.example"


def test_a_search_asks_for_what_the_page_chose(service: Service) -> None:
    service.answer(
        "/api/v1/search/text",
        {
            "items": [],
            "limit": 5,
            "offset": 10,
            "has_more": False,
            "model": "m",
            "query_truncated": False,
        },
    )

    client_module.client().search("a blue circle", limit=5, offset=10, min_score=0.2, tag=None)

    (query,) = service.queries("/api/v1/search/text")
    assert query == {"q": "a blue circle", "limit": "5", "offset": "10", "min_score": "0.2"}


def test_a_threshold_that_was_not_chosen_is_not_sent(service: Service) -> None:
    service.answer(
        "/api/v1/search/text",
        {
            "items": [],
            "limit": 5,
            "offset": 0,
            "has_more": False,
            "model": "m",
            "query_truncated": False,
        },
    )

    client_module.client().search("dragon", limit=5, offset=0, min_score=None, tag=None)

    assert "min_score" not in service.queries("/api/v1/search/text")[0]


def test_a_tag_narrows_the_results_the_page_shows(service: Service) -> None:
    service.answer(
        "/api/v1/search/text",
        {
            "items": [
                {"score": 0.4, "asset": asset("1", tags=["cat"])},
                {"score": 0.3, "asset": asset("2", tags=["dog"])},
            ],
            "limit": 5,
            "offset": 0,
            "has_more": False,
            "model": "m",
            "query_truncated": False,
        },
    )

    found = client_module.client().search("animal", limit=5, offset=0, min_score=None, tag="dog")

    assert [item["asset"]["id"] for item in found["items"]] == ["2"]


def test_listing_passes_the_tag_filter_the_api_takes(service: Service) -> None:
    service.answer("/api/v1/assets", {"items": [], "limit": 12, "offset": 0, "has_more": False})

    client_module.client().assets(limit=12, offset=24, tags_all="demo")

    assert service.queries("/api/v1/assets") == [
        {"limit": "12", "offset": "24", "tags_all": "demo"}
    ]


def test_an_upload_sends_the_file_and_what_was_typed_beside_it(service: Service) -> None:
    service.answer("/api/v1/assets", asset(), status=201)

    client_module.client().upload(
        name="p.png", data=b"bytes", content_type="image/png", tags="a,b", meta="{}"
    )

    request = service.asked[-1]
    assert request.method == "POST"
    body = request.content.decode("latin-1")
    assert 'filename="p.png"' in body and "a,b" in body


def test_a_deletion_asks_for_the_asset_and_accepts_no_content(service: Service) -> None:
    service.on("/api/v1/assets/abc", lambda request: httpx.Response(204))

    assert client_module.client().delete("abc") is None
    assert service.asked[-1].method == "DELETE"


def test_a_refusal_is_the_services_own_words(service: Service) -> None:
    service.on(
        "/api/v1/assets",
        lambda request: problem(415, "Unsupported Media Type", "PDF is not a picture."),
    )

    with pytest.raises(ServiceError) as refused:
        client_module.client().upload(
            name="a.pdf", data=b"%PDF", content_type="application/pdf", tags="", meta=""
        )

    assert refused.value.title == "Unsupported Media Type"
    assert refused.value.detail == "PDF is not a picture."


def test_a_refusal_carries_what_else_the_service_said(service: Service) -> None:
    service.on(
        "/ready",
        lambda request: problem(
            503, "Service Unavailable", "not ready", checks={"database": "OperationalError"}
        ),
    )

    with pytest.raises(ServiceError) as refused:
        client_module.client().ready()

    assert refused.value.body["checks"] == {"database": "OperationalError"}


def test_a_refusal_without_problem_details_still_reads_as_a_sentence(service: Service) -> None:
    service.on("/api/v1/stats", lambda request: httpx.Response(500, text="boom"))

    with pytest.raises(ServiceError) as refused:
        client_module.client().stats()

    assert "500" in refused.value.detail
    assert "boom" not in refused.value.detail, "the page shows a sentence, not a body"


def test_a_service_that_cannot_be_reached_is_a_sentence_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    monkeypatch.setenv("API_BASE_URL", "http://service.example")
    made = client_module.Client(httpx.Client(transport=httpx.MockTransport(refuse)))

    with pytest.raises(ServiceError) as refused:
        made.stats()

    assert refused.value.title == "The service is not answering"
    assert "service.example" in refused.value.detail


def test_a_picture_is_addressed_from_the_link_the_api_gave(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("API_BASE_URL", "http://service.example")

    assert (
        address_of("/api/v1/assets/7/thumbnail")
        == "http://service.example/api/v1/assets/7/thumbnail"
    )
    assert address_of("api/v1/assets/7/file") == "http://service.example/api/v1/assets/7/file"
