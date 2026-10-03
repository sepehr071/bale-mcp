"""Calls the real Bale Bot API with BALE_BOT_TOKEN.

Read-only: pytest -m live
Sends one message to BALE_TEST_CHAT_ID (owner approval needed): pytest -m live_send
"""

import os

import pytest

pytestmark = [
    pytest.mark.anyio,
    pytest.mark.skipif(not os.environ.get("BALE_BOT_TOKEN"), reason="BALE_BOT_TOKEN not set"),
]


async def call(client, name, args=None):
    result = await client.call_tool(name, args or {})
    assert not result.is_error, result.content[0].text
    return result.structured_content


@pytest.mark.live
async def test_get_me(client):
    me = await call(client, "bot_get_me")
    assert me["is_bot"] is True and me["username"]


@pytest.mark.live
async def test_webhook_and_updates(client):
    info = await call(client, "bot_get_webhook_info")
    if not info["url"]:
        out = await call(client, "bot_get_new_messages", {"limit": 5})
        assert isinstance(out["messages"], list)


@pytest.mark.live_send
@pytest.mark.skipif(not os.environ.get("BALE_TEST_CHAT_ID"), reason="BALE_TEST_CHAT_ID not set")
async def test_send_edit_delete(client):
    chat = int(os.environ["BALE_TEST_CHAT_ID"])
    sent = await call(client, "bot_send_message", {"chat_id": chat, "text": "bale-mcp live test"})
    edited = await call(
        client,
        "bot_edit_message",
        {"chat_id": chat, "message_id": sent["message_id"], "text": "bale-mcp live test (edited)"},
    )
    assert edited.get("text", "").endswith("(edited)") or edited.get("edited")
    assert (await call(client, "bot_delete_message", {"chat_id": chat, "message_id": sent["message_id"]}))["deleted"]
