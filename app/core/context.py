"""Request context read back from structlog's context variables."""

import structlog

UNKNOWN_REQUEST_ID = "unknown"


def current_request_id() -> str:
    """The id bound to the current request, or `unknown` outside one."""
    value = structlog.contextvars.get_contextvars().get("request_id")
    return value if isinstance(value, str) else UNKNOWN_REQUEST_ID
