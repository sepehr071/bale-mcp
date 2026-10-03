import json

import httpx
import pytest
from mcp import Client

from bale_mcp import http, store
from bale_mcp.server import mcp

FAKE_TOKEN = "123456789:FAKEtokenFAKEtokenFAKEtokenFAKEtoken12"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def fresh_http_client():
    """The shared httpx client is bound to one event loop; each test gets a new loop."""
    http.set_transport(None)
    yield
    http.set_transport(None)


@pytest.fixture(autouse=True)
def fresh_store(monkeypatch):
    """Each test gets an empty in-memory message store and no chat allowlist."""
    monkeypatch.setenv("BALE_MCP_DB", ":memory:")
    monkeypatch.delenv("BALE_ALLOWED_CHATS", raising=False)
    store.reset()
    yield
    store.reset()


@pytest.fixture
def api(monkeypatch):
    """Fake Bot API: api["getMe"] = result, or a callable(request) -> httpx.Response.

    Keys are Bot API method names. A plain value is wrapped as {"ok": true, "result": value}.
    Every request is appended to api.calls; api.body(i) returns its JSON body.
    """
    monkeypatch.setenv("BALE_BOT_TOKEN", FAKE_TOKEN)

    class Routes(dict):
        calls: list[httpx.Request]

        def body(self, i=-1):
            return json.loads(self.calls[i].content)

    routes = Routes()
    routes.calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        routes.calls.append(request)
        target = routes.get(request.url.path.rsplit("/", 1)[-1])
        if target is None:
            return httpx.Response(404, json={"ok": False, "error_code": 404, "description": "Not Found"})
        if callable(target):
            return target(request)
        return httpx.Response(200, json={"ok": True, "result": target})

    http.set_transport(httpx.MockTransport(handler))
    return routes


@pytest.fixture
async def client():
    async with Client(mcp, raise_exceptions=True) as c:
        yield c
