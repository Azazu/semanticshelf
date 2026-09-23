"""The only thing in the demo interface that speaks HTTP.

The interface is a client of the service and nothing else: it holds no database
session, reads no file, loads no model, and imports nothing from `app`. Every
call it makes goes through this module, which means the timeout is set once and
a refusal is turned into a person's sentence once — with the words the service
chose, because the service already wrote them for a person (RFC 9457 problem
details carry a `title` and a `detail`).

Pictures are the exception that proves the rule: this module never fetches one.
It builds the address the API gave (`links.thumbnail`, `links.file`) and the
browser asks the service for the bytes directly.
"""

import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import httpx

#: Where the service is. The default is the port `make run` uses, so a demo on
#: one machine needs no configuration at all.
DEFAULT_BASE_URL = "http://127.0.0.1:8000"

#: Long enough for a search that loads a model on its first call, short enough
#: that a page does not hang on a service that is not answering.
TIMEOUT_SECONDS = 30.0

API = "/api/v1"


class ServiceError(Exception):
    """Something the service refused, or could not be asked at all.

    `title` and `detail` are what a page shows. They come from the service when
    it answered, and from this module only when it did not.
    """

    def __init__(self, title: str, detail: str, body: dict[str, Any] | None = None) -> None:
        super().__init__(f"{title}: {detail}")
        self.title = title
        self.detail = detail
        #: Whatever else the service said — `/ready` puts its per-check reasons
        #: here, and the status page shows them.
        self.body = body or {}


def base_url() -> str:
    """The service's address, read at call time so a test can change it."""
    return os.environ.get("API_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def address_of(link: str) -> str:
    """The absolute address of something the API linked to.

    The API answers with paths (`/api/v1/assets/<id>/thumbnail`); a browser
    needs the host in front of them. Nothing here invents a link the API did
    not give.
    """
    return urljoin(base_url() + "/", link.lstrip("/"))


@dataclass(frozen=True, slots=True)
class Client:
    """A thin wrapper over one `httpx.Client`, made per page run."""

    http: httpx.Client

    def _ask(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = self.http.request(method, f"{base_url()}{path}", **kwargs)
        except httpx.HTTPError as error:
            raise ServiceError(
                "The service is not answering",
                f"Nothing answered at {base_url()}. Is it running? ({error})",
            ) from error
        if response.status_code >= 400:
            raise _refusal(response)
        if response.status_code == httpx.codes.NO_CONTENT:
            return None
        try:
            return response.json()
        except ValueError as error:  # pragma: no cover - the service always answers JSON
            raise ServiceError(
                "The service answered something unexpected",
                f"{response.status_code} with a body that is not JSON.",
            ) from error

    # --- what the pages ask for -------------------------------------------------

    def search(
        self, query: str, *, limit: int, offset: int, min_score: float | None, tag: str | None
    ) -> dict[str, Any]:
        parameters: dict[str, Any] = {"q": query, "limit": limit, "offset": offset}
        if min_score is not None:
            parameters["min_score"] = min_score
        found: dict[str, Any] = self._ask("GET", f"{API}/search/text", params=parameters)
        if tag:
            kept = [item for item in found["items"] if tag in item["asset"]["tags"]]
            found = {**found, "items": kept}
        return found

    def search_image(
        self,
        *,
        name: str,
        data: bytes,
        content_type: str,
        limit: int,
        offset: int,
        min_score: float | None,
    ) -> dict[str, Any]:
        """A picture as the query. The page fields travel beside the file."""
        form = {"limit": str(limit), "offset": str(offset)}
        if min_score is not None:
            form["min_score"] = str(min_score)
        found: dict[str, Any] = self._ask(
            "POST",
            f"{API}/search/image",
            files={"file": (name, data, content_type)},
            data=form,
        )
        return found

    def similar(
        self, identifier: str, *, limit: int, offset: int, min_score: float | None
    ) -> dict[str, Any]:
        """The neighbours of a stored asset, under the service's own default model."""
        parameters: dict[str, Any] = {"limit": limit, "offset": offset}
        if min_score is not None:
            parameters["min_score"] = min_score
        found: dict[str, Any] = self._ask(
            "GET", f"{API}/assets/{identifier}/similar", params=parameters
        )
        return found

    def assets(self, *, limit: int, offset: int, tags_all: str | None = None) -> dict[str, Any]:
        parameters: dict[str, Any] = {"limit": limit, "offset": offset}
        if tags_all:
            parameters["tags_all"] = tags_all
        page: dict[str, Any] = self._ask("GET", f"{API}/assets", params=parameters)
        return page

    def asset(self, identifier: str) -> dict[str, Any]:
        one: dict[str, Any] = self._ask("GET", f"{API}/assets/{identifier}")
        return one

    def upload(
        self, *, name: str, data: bytes, content_type: str, tags: str, meta: str
    ) -> dict[str, Any]:
        form = {key: value for key, value in (("tags", tags), ("meta", meta)) if value}
        created: dict[str, Any] = self._ask(
            "POST",
            f"{API}/assets",
            files={"file": (name, data, content_type)},
            data=form,
        )
        return created

    def delete(self, identifier: str) -> None:
        self._ask("DELETE", f"{API}/assets/{identifier}")

    def tags(self, *, limit: int = 50) -> dict[str, Any]:
        found: dict[str, Any] = self._ask("GET", f"{API}/tags", params={"limit": limit})
        return found

    def stats(self) -> dict[str, Any]:
        found: dict[str, Any] = self._ask("GET", f"{API}/stats")
        return found

    def ready(self) -> dict[str, Any]:
        """Readiness, as the probe answers it.

        A service that is not ready answers 503 problem details whose `checks`
        member names each check's outcome, so the refusal carries what the page
        wants to show and is raised like any other.
        """
        answered: dict[str, Any] = self._ask("GET", "/ready")
        return answered


def _refusal(response: httpx.Response) -> ServiceError:
    """The service's own words, when it wrote any."""
    try:
        body = response.json()
    except ValueError:
        body = {}
    if isinstance(body, dict) and ("title" in body or "detail" in body):
        return ServiceError(
            str(body.get("title") or response.reason_phrase),
            str(body.get("detail") or "The service gave no further detail."),
            body,
        )
    return ServiceError(
        response.reason_phrase or "The service refused",
        f"It answered {response.status_code} and said nothing more.",
    )


def client() -> Client:
    """One client for one page run."""
    return Client(httpx.Client(timeout=TIMEOUT_SECONDS, follow_redirects=False))
