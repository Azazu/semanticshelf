"""A service that answers from memory, and the pages pointed at it.

Nothing here starts a server or opens a database: the interface's one HTTP
client is given an `httpx.MockTransport`, which is also what lets a test say
"and then the page asked for exactly this".
"""

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest

from ui import client as client_module
from ui import shell

pytestmark = pytest.mark.ui

THUMBNAIL = "/api/v1/assets/{id}/thumbnail"
FILE = "/api/v1/assets/{id}/file"


def asset(
    identifier: str = "a" * 8,
    *,
    name: str = "picture.png",
    tags: list[str] | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": identifier,
        "created_at": "2026-09-23T10:00:00Z",
        "content_type": "image/png",
        "width": 64,
        "height": 64,
        "size_bytes": 1024,
        "sha256": "0" * 64,
        "original_filename": name,
        "source": "folder",
        "tags": tags if tags is not None else ["demo"],
        "meta": meta if meta is not None else {"dataset": "coco-val2017"},
        "index_status": {"clip-vit-l14": "done"},
        "links": {"file": FILE.format(id=identifier), "thumbnail": THUMBNAIL.format(id=identifier)},
    }


def problem(status: int, title: str, detail: str, **extra: Any) -> httpx.Response:
    body = {"type": "/errors/example", "title": title, "status": status, "detail": detail, **extra}
    return httpx.Response(status, json=body, headers={"content-type": "application/problem+json"})


@dataclass
class Service:
    """What the stub answers, and what it was asked."""

    routes: dict[str, Callable[[httpx.Request], httpx.Response]] = field(default_factory=dict)
    asked: list[httpx.Request] = field(default_factory=list)

    def on(self, path: str, handler: Callable[[httpx.Request], httpx.Response]) -> None:
        self.routes[path] = handler

    def answer(self, path: str, body: Any, status: int = 200) -> None:
        self.on(path, lambda request: httpx.Response(status, json=body))

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.asked.append(request)
        handler = self.routes.get(request.url.path)
        if handler is None:
            return problem(404, "Not Found", f"nothing stubbed for {request.url.path}")
        return handler(request)

    def paths(self) -> list[str]:
        return [request.url.path for request in self.asked]

    def queries(self, path: str) -> list[dict[str, str]]:
        return [dict(r.url.params) for r in self.asked if r.url.path == path]


@pytest.fixture
def service(monkeypatch: pytest.MonkeyPatch) -> Iterator[Service]:
    stub = Service()
    monkeypatch.setenv("API_BASE_URL", "http://service.example")

    def made() -> client_module.Client:
        transport = httpx.MockTransport(stub.handle)
        return client_module.Client(httpx.Client(transport=transport))

    monkeypatch.setattr(shell, "service", made)
    monkeypatch.setattr(client_module, "client", made)
    yield stub


@pytest.fixture
def searched(service: Service) -> Service:
    service.answer(
        "/api/v1/search/text",
        {
            "items": [{"score": 0.31, "asset": asset("11111111", name="blue.png")}],
            "limit": 12,
            "offset": 0,
            "has_more": False,
            "model": "clip-vit-l14",
            "query_truncated": False,
        },
    )
    return service


def page_of(items: list[dict[str, Any]], *, has_more: bool = False) -> dict[str, Any]:
    return {"items": items, "limit": 12, "offset": 0, "has_more": has_more}


def meta_json(**values: Any) -> str:
    return json.dumps(values)
