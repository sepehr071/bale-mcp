import logging

import httpx
import pytest
from conftest import FAKE_TOKEN

pytestmark = pytest.mark.anyio

SENDING = {"bot_send_message", "bot_send_file", "bot_edit_message", "bot_delete_message"}
READING = {
    "bot_get_me",
    "bot_get_chat",
    "bot_get_webhook_info",
    "bot_get_new_messages",
    "bot_list_chats",
    "bot_read_chat",
}
READING |= {"bot_search_messages", "bot_wait_for_reply", "bot_download_file"}
MSG = {
    "message_id": 7,
    "date": 1791025477,
    "chat": {"id": 111111111, "type": "private", "first_name": "Test"},
    "from": {"id": 111111111, "is_bot": False, "first_name": "Test"},
    "text": "/start",
}
MEDIA = {k: v for k, v in MSG.items() if k != "text"}  # media messages carry a caption, not text


async def call(client, name, args=None):
    result = await client.call_tool(name, args or {})
    assert not result.is_error, result.content[0].text
    return result.structured_content


async def error(client, name, args=None):
    result = await client.call_tool(name, args or {})
    assert result.is_error
    return result.content[0].text


async def test_annotations(client):
    tools = {t.name: t for t in (await client.list_tools()).tools}
    assert set(tools) == SENDING | READING
    for name, t in tools.items():
        assert t.title and t.description, name
        assert t.annotations.read_only_hint is (name not in SENDING), name
        assert t.annotations.destructive_hint is (name in SENDING), name


async def test_missing_token(client, monkeypatch):
    monkeypatch.delenv("BALE_BOT_TOKEN", raising=False)
    assert "BALE_BOT_TOKEN is not set" in await error(client, "bot_get_me")


async def test_get_me(client, api):
    api["getMe"] = {"id": 42, "is_bot": True, "first_name": "MCP", "username": "mcp_bot", "can_join_groups": True}
    assert await call(client, "bot_get_me") == {"id": 42, "username": "mcp_bot", "first_name": "MCP", "is_bot": True}
    assert api.calls[0].url.path == f"/bot{FAKE_TOKEN}/getMe"


async def test_bad_token_is_actionable_and_redacted(client, api):
    text = await error(client, "bot_get_chat", {"chat_id": 5})
    assert "rejected the bot token" in text and FAKE_TOKEN not in text
    api["getMe"] = lambda r: httpx.Response(
        403, json={"ok": False, "error_code": 403, "description": "Bad Request: Token not found"}
    )
    assert "rejected the bot token (HTTP 403)" in await error(client, "bot_get_me")  # seen from tapi.bale.ai 2026-10


async def test_httpx_does_not_log_urls():
    """Request URLs hold the token; httpx logs them at INFO."""
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
    assert logging.getLogger("httpcore").getEffectiveLevel() >= logging.WARNING


async def test_upstream_text_is_redacted(client, api, monkeypatch):
    api["getChat"] = lambda r: httpx.Response(
        400, json={"ok": False, "error_code": 400, "description": f"bad request for {FAKE_TOKEN}"}
    )
    text = await error(client, "bot_get_chat", {"chat_id": 5})
    assert FAKE_TOKEN not in text and "***" in text
    monkeypatch.setenv("BALE_BOT_TOKEN", FAKE_TOKEN + "\n")  # pasted with a newline: requests strip it, so must redact
    assert FAKE_TOKEN not in await error(client, "bot_get_chat", {"chat_id": 5})


async def test_webhook_conflict(client, api):
    api["getUpdates"] = lambda r: httpx.Response(
        409, json={"ok": False, "error_code": 409, "description": "Conflict: webhook is active"}
    )
    assert "bot_get_webhook_info" in await error(client, "bot_get_new_messages")


async def test_rate_limit(client, api):
    api["getMe"] = lambda r: httpx.Response(
        429, json={"ok": False, "error_code": 429, "description": "Too Many Requests", "parameters": {"retry_after": 7}}
    )
    assert "Retry after 7 seconds" in await error(client, "bot_get_me")


async def test_webhook_info(client, api):
    api["getWebhookInfo"] = {"url": "", "pending_update_count": 3}
    assert (await call(client, "bot_get_webhook_info"))["pending_update_count"] == 3


async def test_send_message(client, api):
    api["sendMessage"] = {
        **MSG,
        "message_id": 8,
        "text": "سلام",
        "from": {"id": 42, "is_bot": True, "first_name": "MCP"},
    }
    out = await call(client, "bot_send_message", {"chat_id": 111111111, "text": "سلام", "reply_to_message_id": 7})
    assert out["message_id"] == 8 and out["text"] == "سلام"
    assert api.body() == {"chat_id": 111111111, "text": "سلام", "reply_to_message_id": 7}


async def test_send_file_by_url(client, api):
    api["sendPhoto"] = {**MEDIA, "message_id": 9, "photo": [{"file_id": "x"}], "caption": "hi"}
    out = await call(
        client,
        "bot_send_file",
        {"chat_id": "@chan", "kind": "photo", "source": "https://example.com/a.jpg", "caption": "hi"},
    )
    assert out["kind"] == "photo" and out["text"] == "hi"
    assert api.body() == {"chat_id": "@chan", "caption": "hi", "photo": "https://example.com/a.jpg"}


async def test_send_file_local_upload(client, api, tmp_path):
    f = tmp_path / "report.pdf"
    f.write_bytes(b"%PDF-1.4 test")
    api["sendDocument"] = {**MEDIA, "message_id": 10, "document": {"file_id": "d"}}
    out = await call(client, "bot_send_file", {"chat_id": 1, "kind": "document", "source": str(f)})
    assert out["kind"] == "document"
    body = api.calls[-1].content
    assert b"report.pdf" in body and b"%PDF-1.4 test" in body


async def test_send_file_missing_local_file(client, api, tmp_path):
    assert "File not found" in await error(
        client, "bot_send_file", {"chat_id": 1, "kind": "document", "source": str(tmp_path / "nope.pdf")}
    )
    assert api.calls == []


async def test_edit_and_delete(client, api):
    # What tapi.bale.ai really returns (2026-10): a stub with message_id 0 and no text.
    api["editMessageText"] = {
        "message_id": 0,
        "date": 1791029225,
        "chat": {"id": 1, "type": "private", "photo": None},
        "edit_date": 1791029225,
    }
    assert await call(client, "bot_edit_message", {"chat_id": 1, "message_id": 7, "text": "edited"}) == {
        "edited": True,
        "message_id": 7,
    }
    api["deleteMessage"] = True
    assert await call(client, "bot_delete_message", {"chat_id": 1, "message_id": 7}) == {"deleted": True}
