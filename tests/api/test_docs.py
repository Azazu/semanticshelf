"""OpenAPI document and Swagger UI locations."""

import httpx

from app import __version__


async def test_openapi_document(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/openapi.json")
    assert response.status_code == 200
    document = response.json()
    assert document["openapi"].startswith("3.1")
    assert document["info"]["version"] == __version__
    assert {"/health", "/ready"} <= document["paths"].keys()
    # The probes stay outside the versioned API; the resources live inside it.
    assert not any(path.startswith("/api/v1") for path in ("/health", "/ready"))
    assert "/api/v1/assets" in document["paths"]
    for path, operations in document["paths"].items():
        for operation in operations.values():
            assert operation.get("summary"), path
            assert operation.get("description"), path
    ready = document["paths"]["/ready"]["get"]["responses"]
    assert set(ready["503"]["content"]) == {"application/problem+json"}
    schema_ref = ready["503"]["content"]["application/problem+json"]["schema"]["$ref"]
    assert schema_ref.endswith("/NotReadyProblem")
    for path, operations in document["paths"].items():
        for operation in operations.values():
            for status, response in operation["responses"].items():
                if int(status) >= 400:
                    assert set(response["content"]) == {"application/problem+json"}, (path, status)


async def test_swagger_ui_and_no_redoc(client: httpx.AsyncClient) -> None:
    docs = await client.get("/api/docs")
    assert docs.status_code == 200
    assert "text/html" in docs.headers["content-type"]
    assert (await client.get("/api/redoc")).status_code == 404
