"""Bale Bot API tools (Telegram-style API at tapi.bale.ai), authenticated with BALE_BOT_TOKEN."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field

from . import store
from .http import ApiError, request
from .registry import tool

BOT_BASE = "https://tapi.bale.ai"
MAX_UPLOAD = 50 * 1024 * 1024  # Bale's documented bot upload limit

ChatId = Annotated[
    int | str,
    Field(
        description="Chat id (number from bot_get_new_messages or bot_list_chats, e.g. 123456789) or a public channel/group username like '@mychannel'."
    ),
]


def token() -> str:
    t = os.environ.get("BALE_BOT_TOKEN", "").strip()
    if not t:
        raise ApiError(
            "BALE_BOT_TOKEN is not set. Create a bot with @botfather (https://ble.ir/botfather) and set the token."
        )
    return t


def allowed(chat_id: int | str, username: str | None = None) -> bool:
    """False when BALE_ALLOWED_CHATS is set and lists neither the chat id nor its @username.

    The store maps a known chat's id and @username to each other, so either form matches either listing.
    """
    allow = {s.strip().lower() for s in os.environ.get("BALE_ALLOWED_CHATS", "").split(",") if s.strip()}
    if not allow:
        return True
    names = store.aliases(chat_id) | ({f"@{username}".lower()} if username else set())
    return bool(allow & names)


async def call(method: str, params: dict[str, Any] | None = None, files: dict[str, Any] | None = None) -> Any:
    """Call a Bot API method and return its `result`. Chats outside BALE_ALLOWED_CHATS are refused here."""
    url = f"{BOT_BASE}/bot{token()}/{method}"
    params = {k: v for k, v in (params or {}).items() if v is not None}
    if "chat_id" in params and not allowed(params["chat_id"]):
        raise ApiError(f"Chat {params['chat_id']} is not in BALE_ALLOWED_CHATS, so this server will not contact it.")
    if files:
        r = await request("POST", url, data={k: str(v) for k, v in params.items()}, files=files)
    else:
        r = await request("POST", url, json=params)
    try:
        body = r.json()
    except ValueError as e:
        raise ApiError(f"Bale Bot API returned a non-JSON response (HTTP {r.status_code}).", r.status_code) from e
    if isinstance(body, dict) and body.get("ok"):
        return body.get("result")
    code = body.get("error_code", r.status_code) if isinstance(body, dict) else r.status_code
    desc = str(body.get("description", "")) if isinstance(body, dict) else ""
    if (code == 404 and desc.lower() in ("not found", "")) or "token not found" in desc.lower():
        raise ApiError(
            f"Bale rejected the bot token (HTTP {code}). Check BALE_BOT_TOKEN; get a new one from @botfather.", code
        )
    if code == 429:
        wait = (body.get("parameters") or {}).get("retry_after") if isinstance(body, dict) else None
        raise ApiError(f"Bale is rate limiting this bot (HTTP 429). Retry after {wait or 'a few'} seconds.", 429)
    if code == 409 or "webhook" in desc.lower():
        raise ApiError(
            f"{desc or 'Conflict'} (HTTP {code}). A webhook is probably set; check bot_get_webhook_info.", code
        )
    raise ApiError(f"Bale Bot API error (HTTP {code}): {desc[:300]}", code)


def _iso(ts: int | None) -> str | None:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat() if ts else None


def _chat(c: dict[str, Any] | None) -> dict[str, Any] | None:
    if not c:
        return None
    return {k: c.get(k) for k in ("id", "type", "title", "username", "first_name", "last_name") if c.get(k) is not None}


def _message(m: dict[str, Any]) -> dict[str, Any]:
    kinds = ("text", "photo", "document", "video", "animation", "audio", "voice", "sticker", "location", "contact")
    kind = next((k for k in kinds if k in m), "other")
    media = m.get(kind)
    if kind == "photo" and isinstance(media, list) and media:
        media = media[-1]  # sizes ascend; the last is the original
    out = {
        "message_id": m.get("message_id"),
        "chat": _chat(m.get("chat")),
        "from": _chat(m.get("from")),
        "date": _iso(m.get("date")),
        "kind": kind,
        "text": m.get("text") or m.get("caption"),
    }
    if isinstance(media, dict) and media.get("file_id"):
        out["file_id"], out["file_name"] = media["file_id"], media.get("file_name")
    if m.get("reply_to_message"):
        out["reply_to_message_id"] = m["reply_to_message"].get("message_id")
    return {k: v for k, v in out.items() if v is not None}


def _sent(m: dict[str, Any]) -> dict[str, Any]:
    """Normalize a message the bot just sent and keep it in the local store."""
    out = _message(m)
    store.save(out, outgoing=True)
    return out


@tool("Bot: who am I")
async def bot_get_me() -> dict[str, Any]:
    """Check BALE_BOT_TOKEN and show the bot's id, username and name. Use first to confirm the bot works."""
    me = await call("getMe")
    return {k: me.get(k) for k in ("id", "username", "first_name", "is_bot") if k in me}


@tool("Bot: chat info")
async def bot_get_chat(chat_id: ChatId) -> dict[str, Any]:
    """Get a chat's type, title or name, username and description, as seen by the bot."""
    c = await call("getChat", {"chat_id": chat_id})
    out = _chat(c) or {}
    if c.get("description"):
        out["description"] = c["description"]
    return out


@tool("Bot: webhook status")
async def bot_get_webhook_info() -> dict[str, Any]:
    """Show whether a webhook is set (url empty = the reading tools work), pending updates and the last error."""
    w = await call("getWebhookInfo")
    return {
        "url": w.get("url") or "",
        "pending_update_count": w.get("pending_update_count"),
        "last_error_message": w.get("last_error_message"),
        "last_error_date": _iso(w.get("last_error_date")),
    }


@tool("Bot: send message", sends=True)
async def bot_send_message(
    chat_id: ChatId,
    text: Annotated[str, Field(min_length=1, max_length=4096, description="Message text.")],
    reply_to_message_id: Annotated[int | None, Field(description="Reply to this message id in the same chat.")] = None,
    buttons: Annotated[
        list[list[Annotated[str, Field(min_length=1)]]] | None,
        Field(
            description="Inline buttons as rows of labels, e.g. [['Yes', 'No']]. A press arrives as a message of kind 'button' whose text is the label (cut to 64 bytes); bot_wait_for_reply returns it."
        ),
    ] = None,
) -> dict[str, Any]:
    """Send a text message from the bot. Sends a real message. Confirm recipient and text with the user before calling.

    Bale formats all text as Markdown (*bold*, _italic_). The user must have started the bot first (sent it /start)
    or the bot must be a member of the group/channel. To ask a question and get the answer, send it (with buttons
    if the choices are fixed), then call bot_wait_for_reply with the returned message_id.
    """
    markup = None
    if buttons:
        rows = [[{"text": b, "callback_data": b.encode()[:64].decode(errors="ignore")} for b in row] for row in buttons]
        markup = {"inline_keyboard": rows}
    params = {"chat_id": chat_id, "text": text, "reply_to_message_id": reply_to_message_id, "reply_markup": markup}
    return _sent(await call("sendMessage", params))


FileKind = Literal["photo", "document", "video", "audio", "voice"]
METHOD = {
    "photo": "sendPhoto",
    "document": "sendDocument",
    "video": "sendVideo",
    "audio": "sendAudio",
    "voice": "sendVoice",
}


@tool("Bot: send file", sends=True)
async def bot_send_file(
    chat_id: ChatId,
    kind: Annotated[FileKind, Field(description="How Bale should show the file.")],
    source: Annotated[str, Field(min_length=1, description="An http(s) URL, or a path to a local file (max 50 MB).")],
    caption: Annotated[str | None, Field(max_length=1024, description="Optional caption.")] = None,
) -> dict[str, Any]:
    """Send a photo, document, video, audio or voice file from the bot. Sends a real message. Confirm recipient and file with the user before calling."""
    params: dict[str, Any] = {"chat_id": chat_id, "caption": caption}
    if source.startswith(("http://", "https://")):
        params[kind] = source
        m = await call(METHOD[kind], params)
    else:
        path = Path(source).expanduser()
        if not path.is_file():
            raise ApiError(f"File not found: {path}")
        size = path.stat().st_size
        if size > MAX_UPLOAD:
            raise ApiError(f"{path.name} is {size // (1024 * 1024)} MB; Bale bots can upload at most 50 MB.")
        with path.open("rb") as f:
            m = await call(METHOD[kind], params, files={kind: (path.name, f)})
    return _sent(m)


@tool("Bot: edit message", sends=True)
async def bot_edit_message(
    chat_id: ChatId,
    message_id: Annotated[int, Field(description="Id of a text message the bot sent.")],
    text: Annotated[str, Field(min_length=1, max_length=4096, description="New text.")],
) -> dict[str, Any]:
    """Replace the text of a message the bot sent earlier. Changes a real message. Confirm with the user before calling."""
    m = await call("editMessageText", {"chat_id": chat_id, "message_id": message_id, "text": text})
    store.edit(chat_id, message_id, text, unread=False)  # an '@channel' chat_id matches no stored row; fine
    return {
        "edited": bool(m),
        "message_id": message_id,
    }  # Bale answers with a stub (message_id 0, no text), not the message


@tool("Bot: delete message", sends=True)
async def bot_delete_message(
    chat_id: ChatId,
    message_id: Annotated[int, Field(description="Message id to delete.")],
) -> dict[str, Any]:
    """Delete a message in a chat where the bot may delete it (its own messages, or as admin). Cannot be undone; confirm with the user first."""
    ok = await call("deleteMessage", {"chat_id": chat_id, "message_id": message_id})
    store.delete(chat_id, message_id)
    return {"deleted": bool(ok)}
