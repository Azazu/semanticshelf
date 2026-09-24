"""Request id: honoured from `X-Request-ID` when well-formed, generated otherwise.

A pure ASGI middleware (not `BaseHTTPMiddleware`, which buffers responses and
breaks streaming). It binds `request_id`, `method` and `path` into the structlog
context for the whole request, returns the id in the response header, logs one
`request completed` line with the status code, and renders the 500 for an
unhandled exception itself: it is the outermost application-owned layer, so
Starlette's server-error middleware (whose handlers run after this context is
gone) never sees the exception.
"""

import re
import uuid

import structlog
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import internal_error_response

REQUEST_ID_HEADER = "x-request-id"
#: `\Z`, not `$`: a value that ends in a newline is not of this shape, and an
#: id that is echoed into a header and into every log line must be exactly it
#: (the rule `app/services/tagging.py` states in full).
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}\Z")

log = structlog.stdlib.get_logger(__name__)


def resolve_request_id(headers: list[tuple[bytes, bytes]]) -> str:
    """The client's id when it matches the allowed shape, else a fresh UUID4."""
    for name, value in headers:
        if name.lower() == REQUEST_ID_HEADER.encode("latin-1"):
            candidate = value.decode("latin-1", errors="replace")
            if _VALID_REQUEST_ID.match(candidate):
                return candidate
            break
    return str(uuid.uuid4())


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = resolve_request_id(scope["headers"])
        status_code = 0

        async def send_with_header(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id, method=scope["method"], path=scope["path"]
        )
        try:
            await self.app(scope, receive, send_with_header)
        except Exception as exc:
            if status_code:
                # The response already started: nothing coherent can be sent any more.
                raise
            log.error("unhandled exception", exc_info=exc)
            await internal_error_response()(scope, receive, send_with_header)
        finally:
            log.info("request completed", status_code=status_code)
            structlog.contextvars.clear_contextvars()
