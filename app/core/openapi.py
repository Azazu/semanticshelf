"""OpenAPI post-processing: error responses are documented under their real media type.

FastAPI documents every declared response model under `application/json`.
Every response at status 400 or higher is problem details here, so the
generated document is rewritten once (and cached, as FastAPI does) to list
those bodies under `application/problem+json`.
"""

from typing import Any

from fastapi import FastAPI

from app.core.errors import PROBLEM_MEDIA_TYPE


def _relabel_error_media_types(schema: dict[str, Any]) -> None:
    for path_item in schema.get("paths", {}).values():
        for operation in path_item.values():
            if not isinstance(operation, dict):
                continue
            for status, response in operation.get("responses", {}).items():
                if not (status.isdigit() and int(status) >= 400):
                    continue
                content = response.get("content")
                if content and "application/json" in content:
                    content[PROBLEM_MEDIA_TYPE] = content.pop("application/json")


def install_problem_media_type(app: FastAPI) -> None:
    original = app.openapi

    def openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = original()
        _relabel_error_media_types(schema)
        app.openapi_schema = schema
        return schema

    app.openapi = openapi  # type: ignore[method-assign]  # FastAPI's documented extension point
