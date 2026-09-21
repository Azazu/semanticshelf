"""The bound on how much of a request body the service will take.

This is the only bound on an uploaded file's size. Two facts about the stack
make it so, both read from the installed packages rather than assumed:
FastAPI parses the whole multipart body before an endpoint runs, so code in
the endpoint cannot refuse anything the parser has already read; and
Starlette's multipart parser applies its `max_part_size` only to parts that
are *not* files, so the parser bounds fields and part counts but never the
file itself.

So the counting happens here, on the ASGI stream, one chunk at a time. It
counts what arrives rather than what a header claims, which is what makes it
hold for a chunked request with no declared length, or one that understates
it. An endpoint that never reads its body never pays for this: `receive` is
only called when something asks for the bytes.
"""

from http import HTTPStatus

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import problem, problem_response

TOO_LARGE_TYPE = "/errors/upload-too-large"


class BodyTooLargeError(Exception):
    """Raised inside `receive`, caught by the middleware that installed it."""


class BodySizeLimitMiddleware:
    """Refuse a request body larger than the configured limit, while it arrives."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        received = 0

        async def counting_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise BodyTooLargeError
            return message

        try:
            await self.app(scope, counting_receive, send)
        except BodyTooLargeError:
            status = HTTPStatus.REQUEST_ENTITY_TOO_LARGE
            response = problem_response(
                problem(
                    status=status,
                    title=status.phrase,
                    detail=f"The request body exceeds the limit of {self.max_bytes} bytes.",
                    type_=TOO_LARGE_TYPE,
                )
            )
            await response(scope, receive, send)
