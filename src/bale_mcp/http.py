"""Shared async HTTP client for the Bale Bot API.

The bot token sits in the URL path, so error messages never include URLs, and upstream
text goes through `redact` before it reaches the model.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import httpx
from mcp.server.mcpserver.exceptions import ToolError

# INFO lines would log request URLs, which hold the token. Set on import so in-process hosts are covered too.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

MAX_CONCURRENCY = 4

_transport: httpx.AsyncBaseTransport | None = None
_client: httpx.AsyncClient | None = None
_limit: asyncio.Semaphore | None = None


class ApiError(ToolError):
    """A failed upstream call. `status` is the HTTP status, or None for network errors."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(redact(message))
        self.status = status


def set_transport(transport: httpx.AsyncBaseTransport | None) -> None:
    """Swap the transport (tests use httpx.MockTransport). Drops the current client."""
    global _transport, _client, _limit
    _transport, _client, _limit = transport, None, None


def redact(text: str) -> str:
    token = os.environ.get("BALE_BOT_TOKEN", "").strip()  # same value the request URLs use
    return text.replace(token, "***") if len(token) >= 8 else text


def _get_client() -> tuple[httpx.AsyncClient, asyncio.Semaphore]:
    global _client, _limit
    if _client is None:
        # System proxy settings are ignored (Iranian services often block foreign exits);
        # BALE_MCP_PROXY opts back in.
        _client = httpx.AsyncClient(
            transport=_transport,
            timeout=30,
            trust_env=False,
            proxy=os.environ.get("BALE_MCP_PROXY") or None,
            headers={"User-Agent": "bale-mcp"},
        )
        _limit = asyncio.Semaphore(MAX_CONCURRENCY)
    assert _limit is not None
    return _client, _limit


async def request(method: str, url: str, **kwargs: Any) -> httpx.Response:
    """Send a request; network failures become ApiError. HTTP status is left to the caller."""
    client, limit = _get_client()
    host = httpx.URL(url).host
    try:
        async with limit:
            return await client.request(method, url, **kwargs)
    except httpx.TimeoutException as e:
        raise ApiError(f"{host} did not answer in time. Try again in a moment.") from e
    except httpx.RequestError as e:
        raise ApiError(
            f"Could not reach {host} ({type(e).__name__}). Check the internet connection; "
            "Bale may refuse some non-Iranian networks (set BALE_MCP_PROXY to route through another proxy)."
        ) from e
