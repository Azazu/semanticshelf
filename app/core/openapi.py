"""OpenAPI post-processing: two corrections to the document FastAPI generates.

FastAPI documents every declared response model under `application/json`.
Every response at status 400 or higher is problem details here, so the
generated document is rewritten once (and cached, as FastAPI does) to list
those bodies under `application/problem+json`.

The second correction is about examples. FastAPI encodes the finished document
with `exclude_none` (`fastapi/openapi/utils.py`, the finishing
`jsonable_encoder`), which drops every null *inside* an example too — so a
field the service really answers with as `null`, a job with no lease and no
error, vanishes from the example while the schema beside it still requires it.
A reader who copies that example gets something that does not parse as the
answer it illustrates, which is worse than showing no example at all. Each
example a route declares is therefore written back into the finished document
exactly as the code wrote it. `tests/api/test_openapi_examples.py` reads the
published document, so a FastAPI whose routes this can no longer walk fails
there rather than quietly publishing examples with holes in them.
"""

from collections.abc import Iterable, Iterator
from typing import Any

from fastapi import FastAPI
from fastapi.routing import APIRoute
from starlette.routing import BaseRoute

from app.core.errors import PROBLEM_MEDIA_TYPE

JSON_MEDIA_TYPE = "application/json"


def _relabel_error_media_types(schema: dict[str, Any]) -> None:
    for path_item in schema.get("paths", {}).values():
        for operation in path_item.values():
            if not isinstance(operation, dict):
                continue
            for status, response in operation.get("responses", {}).items():
                if not (status.isdigit() and int(status) >= 400):
                    continue
                content = response.get("content")
                if content and JSON_MEDIA_TYPE in content:
                    content[PROBLEM_MEDIA_TYPE] = content.pop(JSON_MEDIA_TYPE)


def _api_routes(routes: Iterable[BaseRoute]) -> Iterator[APIRoute]:
    """Every operation the application will publish, whatever the nesting.

    An included router is kept as a wrapper object rather than flattened into
    `app.routes` (FastAPI 0.141), so this descends through whatever a route
    holds: the wrapper's router, or a router's own routes.
    """
    for route in routes:
        if isinstance(route, APIRoute):
            yield route
            continue
        nested = getattr(route, "original_router", None)
        nested_routes = getattr(nested if nested is not None else route, "routes", None)
        if nested_routes:
            yield from _api_routes(nested_routes)


def _declared_examples(app: FastAPI) -> Iterator[tuple[str, str, str, Any]]:
    """Each declared example, with the path, method and status it belongs to."""
    for route in _api_routes(app.routes):
        for status, response in route.responses.items():
            media = response.get("content", {}).get(JSON_MEDIA_TYPE, {})
            if "example" not in media:
                continue
            # A route may key a response by name as well as by number; only a
            # numeric one addresses an entry in the document.
            code = str(int(status)) if isinstance(status, int) else str(status)
            for method in route.methods or ():
                yield route.path_format, method.lower(), code, media["example"]


def _restore_declared_examples(app: FastAPI, schema: dict[str, Any]) -> None:
    for path, method, status, example in _declared_examples(app):
        operation = schema.get("paths", {}).get(path, {}).get(method)
        if not isinstance(operation, dict):  # pragma: no cover - a route kept out of the document
            continue
        content = operation.get("responses", {}).get(status, {}).get("content", {})
        if JSON_MEDIA_TYPE in content:
            content[JSON_MEDIA_TYPE]["example"] = example


def install_document_corrections(app: FastAPI) -> None:
    original = app.openapi

    def openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = original()
        _relabel_error_media_types(schema)
        _restore_declared_examples(app, schema)
        app.openapi_schema = schema
        return schema

    app.openapi = openapi  # type: ignore[method-assign]  # FastAPI's documented extension point
