"""Reading tools: pull updates from Bale into the local store, then read, search and wait on it."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field

from . import store
from .bot import BOT_BASE, FILES_DIR, _chat, _iso, _message, allowed, call, token
from .http import ApiError, download
from .registry import tool

MAX_DOWNLOAD = 20 * 1024 * 1024  # Bale's documented getFile limit
# ponytail: short poll while waiting; getUpdates long polling would cut requests but needs one poller per bot
POLL_SECONDS = 2
MAX_SYNC_PAGES = 20  # Bale keeps at most 2000 updates (20 pages of 100)


async def sync_or_note() -> dict[str, str]:
    """sync() for tools that can answer from the local store: on an API error return a sync_error note instead."""
    try:
        await sync()
    except ApiError as e:
        return {"sync_error": str(e)}
    return {}


async def sync() -> None:
    """Move pending updates from Bale into the local store. Bale keeps them only 24 hours (last 2000)."""
    for _ in range(MAX_SYNC_PAGES):
        updates = await call("getUpdates", {"offset": store.get_offset(), "limit": 100, "timeout": 0}) or []
        for u in updates:
            # An overlapping sync (parallel tool calls, or another process on the same DB) may already have stored it.
            if u["update_id"] >= (store.get_offset() or 0):
                await _save_update(u)
                store.set_offset(u["update_id"] + 1)
        if len(updates) < 100:
            return


async def _save_update(u: dict[str, Any]) -> None:
    """Store one update. Chats outside BALE_ALLOWED_CHATS are dropped here, before anything is kept or shown."""
    for key in ("message", "channel_post", "edited_message", "edited_channel_post"):
        if m := u.get(key):
            n = _message(m)
            c = n.get("chat") or {}
            if "id" in c and allowed(c["id"], c.get("username")):
                if not key.startswith("edited") or not store.edit(
                    c["id"], n.get("message_id"), n.get("text"), unread=True
                ):
                    store.save(n, outgoing=False, update_id=u["update_id"])
            return
    if q := u.get("callback_query"):
        msg = q.get("message") or {}
        c = _chat(msg.get("chat")) or _chat(q.get("from")) or {}
        if "id" not in c or not allowed(c["id"], c.get("username")):
            return
        press = {
            "chat": c,
            "from": _chat(q.get("from")),
            "message_id": msg.get("message_id"),
            "date": _iso(int(time.time())),
            "kind": "button",
            "text": q.get("data"),
        }
        store.save(press, outgoing=False, update_id=u["update_id"])
        try:  # Bale keeps the button spinning until the press is answered
            await call("answerCallbackQuery", {"callback_query_id": q.get("id")})
        except ApiError:
            pass


ChatNumber = Annotated[int, Field(description="Numeric chat id.")]
Limit = Annotated[int, Field(ge=1, le=500, description="Max messages.")]


@tool("Bot: new messages")
async def bot_get_new_messages(limit: Limit = 20) -> dict[str, Any]:
    """Get messages people sent the bot since the last check, from all chats, oldest first, and mark them read.

    Messages carry chat_id, kind, text and file_id for media. Fails while a webhook is set.
    """
    await sync()
    return {"messages": store.take_unread(limit=limit), "unread_left": store.unread_count()}


@tool("Bot: list chats")
async def bot_list_chats(limit: Annotated[int, Field(ge=1, le=500, description="Max chats.")] = 20) -> dict[str, Any]:
    """List the chats this bot has talked in, newest first, with unread count and last message."""
    note = await sync_or_note()
    return {"chats": store.chats(limit), **note}


@tool("Bot: read chat")
async def bot_read_chat(chat_id: ChatNumber, limit: Limit = 20) -> dict[str, Any]:
    """Show a chat's recent messages in both directions, oldest first, and mark the chat read (local store; Bale keeps no history)."""
    note = await sync_or_note()
    return {"messages": store.history(chat_id, limit), **note}


@tool("Bot: search messages")
async def bot_search_messages(
    query: Annotated[str, Field(min_length=1, description="Text to find.")],
    chat_id: Annotated[int | None, Field(description="Only this chat.")] = None,
    limit: Limit = 20,
    max_chars: Annotated[int, Field(ge=50, le=4096, description="Cut each text to this length.")] = 500,
) -> dict[str, Any]:
    """Search stored messages by text, newest first. Persian/Arabic yeh, kaf, digits and ZWNJ match each other.

    Long texts are cut; bot_read_chat shows them whole.
    """
    note = await sync_or_note()
    found = store.search(query, chat_id, limit)
    for m in found:
        if len(t := m.get("text") or "") > max_chars:
            m["text"] = f"{t[:max_chars]}...(+{len(t) - max_chars} chars)"
    return {"messages": found, **note}


@tool("Bot: wait for reply")
async def bot_wait_for_reply(
    chat_id: ChatNumber,
    after_message_id: Annotated[
        int | None,
        Field(description="Only messages newer than this id (the message_id you sent)."),
    ] = None,
    timeout_seconds: Annotated[int, Field(ge=0, le=600, description="Seconds to wait.")] = 60,
) -> dict[str, Any]:
    """Wait until someone writes in a chat or presses a button, then return the new messages (marked read).

    Use after bot_send_message. Returns timed_out=true if nobody answered.
    """
    if not allowed(chat_id):
        raise ApiError(f"Chat {chat_id} is not in BALE_ALLOWED_CHATS, so its messages are never kept.")
    deadline = time.monotonic() + timeout_seconds
    while True:
        await sync()
        messages = store.take_unread(chat_id, after_message_id)
        if messages or time.monotonic() >= deadline:
            return {"messages": messages, "timed_out": not messages}
        await asyncio.sleep(POLL_SECONDS)


@tool("Bot: download file")
async def bot_download_file(
    file_id: Annotated[str, Field(min_length=1, description="file_id from a received message.")],
    folder: Annotated[str | None, Field(description="Save folder (default ~/.bale-mcp/files).")] = None,
) -> dict[str, Any]:
    """Download a file someone sent the bot (max 20 MB) and return its local path. Never overwrites (-1, -2, ... suffix)."""
    f = await call("getFile", {"file_id": file_id})
    remote = (f or {}).get("file_path")
    if not remote or (f.get("file_size") or 0) > MAX_DOWNLOAD:
        raise ApiError("Bale returned no downloadable file. Bots can download files up to 20 MB.")
    status, body = await download(f"{BOT_BASE}/file/bot{token()}/{remote}", MAX_DOWNLOAD)
    if status != 200:
        raise ApiError(f"Bale refused the download (HTTP {status}).", status)
    name = Path(remote).name
    name = "file" if name in ("", ".", "..") else name  # file_path comes from the server; keep it inside the folder
    dest = Path(folder).expanduser() if folder else FILES_DIR
    dest.mkdir(parents=True, exist_ok=True, mode=0o700)
    target, n = dest / name, 0
    while True:
        try:
            with target.open("xb") as out:  # exclusive create: never overwrites, even when racing another call
                out.write(body)
            break
        except FileExistsError:
            n += 1
            target = dest / f"{Path(name).stem}-{n}{Path(name).suffix}"
    return {"path": str(target), "size": len(body)}
