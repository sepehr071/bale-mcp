"""Local SQLite copy of the bot's chats.

The Bot API has no history: Bale keeps updates for 24 hours and forgets them once read. Everything
the bot receives or sends is kept here, on this machine only. BALE_MCP_DB sets the file
(default ~/.bale-mcp/messages.db); BALE_MCP_DB=:memory: keeps nothing on disk.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS chats (id INTEGER PRIMARY KEY, type TEXT, title TEXT, username TEXT);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY,
    update_id INTEGER UNIQUE,  -- incoming only; dedupes updates fetched twice
    chat_id INTEGER NOT NULL,
    message_id INTEGER,        -- for kind 'button': the message the button was on
    outgoing INTEGER NOT NULL,
    unread INTEGER NOT NULL DEFAULT 0,
    sender TEXT, sender_id INTEGER, date TEXT, kind TEXT, text TEXT,
    file_id TEXT, file_name TEXT, reply_to INTEGER
);
CREATE INDEX IF NOT EXISTS messages_chat ON messages (chat_id, date);
CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value INTEGER);
"""

# Search treats Arabic and Persian yeh/kaf, Persian/Arabic/ASCII digits and ZWNJ-joined words alike.
FA = str.maketrans(
    {"\u064a": "\u06cc", "\u0643": "\u06a9", "\u200c": None}
    | {chr(0x6F0 + i): str(i) for i in range(10)}
    | {chr(0x660 + i): str(i) for i in range(10)}
)

_db: sqlite3.Connection | None = None


def fa(text: str | None) -> str:
    return (text or "").translate(FA).lower()


def db() -> sqlite3.Connection:
    global _db
    if _db is None:
        path = os.environ.get("BALE_MCP_DB") or str(Path.home() / ".bale-mcp" / "messages.db")
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        _db = sqlite3.connect(path, isolation_level=None)
        _db.row_factory = sqlite3.Row
        _db.create_function("fa", 1, fa, deterministic=True)
        _db.execute("PRAGMA journal_mode=WAL")  # several MCP processes may share one file
        _db.executescript(SCHEMA)
    return _db


def query(sql: str, args: tuple[Any, ...] | dict[str, Any] = ()) -> list[sqlite3.Row]:
    return db().execute(sql, args).fetchall()


def reset() -> None:
    """Close the connection so the next call reopens BALE_MCP_DB (tests)."""
    global _db
    if _db is not None:
        _db.close()
    _db = None


def aliases(chat: int | str) -> set[str]:
    """Lowercased names of a chat: what was passed, plus its id and @username if the store knows the chat."""
    key = str(chat).lower()
    rows = query("SELECT id, username FROM chats WHERE CAST(id AS TEXT) = ? OR '@' || lower(username) = ?", (key, key))
    return {key} | {str(r["id"]) for r in rows} | {f"@{r['username']}".lower() for r in rows if r["username"]}


def get_offset() -> int | None:
    row = db().execute("SELECT value FROM state WHERE key = 'offset'").fetchone()
    return row[0] if row else None


def set_offset(offset: int) -> None:
    db().execute("INSERT OR REPLACE INTO state VALUES ('offset', ?)", (offset,))


def save(m: dict[str, Any], *, outgoing: bool, update_id: int | None = None) -> None:
    """Store a message as returned by bot._message. Incoming messages start unread."""
    c, f = m["chat"], m.get("from") or {}
    title = c.get("title") or " ".join(filter(None, (c.get("first_name"), c.get("last_name"))))
    db().execute("INSERT OR REPLACE INTO chats VALUES (?, ?, ?, ?)", (c["id"], c.get("type"), title, c.get("username")))
    sender = f.get("title") or " ".join(filter(None, (f.get("first_name"), f.get("last_name")))) or f.get("username")
    db().execute(
        "INSERT OR IGNORE INTO messages (update_id, chat_id, message_id, outgoing, unread, sender, sender_id, date, kind, text, file_id, file_name, reply_to)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (update_id, c["id"], m.get("message_id"), outgoing, not outgoing, sender, f.get("id"), m.get("date"), m.get("kind"),
         m.get("text"), m.get("file_id"), m.get("file_name"), m.get("reply_to_message_id")),
    )  # fmt: skip


def edit(chat_id: int | str, message_id: int | None, text: str | None, *, unread: bool) -> bool:
    cur = db().execute(
        "UPDATE messages SET text = ?, unread = unread OR ? WHERE chat_id = ? AND message_id = ? AND kind != 'button'",
        (text, unread, chat_id, message_id),
    )
    return cur.rowcount > 0


def delete(chat_id: int | str, message_id: int) -> None:
    db().execute(
        "DELETE FROM messages WHERE chat_id = ? AND message_id = ? AND kind != 'button'", (chat_id, message_id)
    )


def row(r: sqlite3.Row) -> dict[str, Any]:
    out = {
        "chat_id": r["chat_id"],
        "message_id": r["message_id"],
        "date": r["date"],
        "from": r["sender"],
        "from_id": r["sender_id"],
        "kind": r["kind"],
        "text": r["text"],
        "file_id": r["file_id"],
        "file_name": r["file_name"],
        "reply_to_message_id": r["reply_to"],
        "outgoing": True if r["outgoing"] else None,
    }
    return {k: v for k, v in out.items() if v is not None}


def take_unread(chat_id: int | None = None, after: int | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """Unread incoming messages, oldest first; marks them read. `after`: only newer than that message id
    (a button press on that message counts)."""
    rows = query(
        "SELECT * FROM messages WHERE unread = 1 AND (:chat IS NULL OR chat_id = :chat)"
        " AND (:after IS NULL OR message_id > :after OR (kind = 'button' AND message_id = :after))"
        " ORDER BY date, message_id LIMIT :limit",
        {"chat": chat_id, "after": after, "limit": limit},
    )
    db().executemany("UPDATE messages SET unread = 0 WHERE id = ?", [(r["id"],) for r in rows])
    return [row(r) for r in rows]


def unread_count() -> int:
    return query("SELECT COUNT(*) FROM messages WHERE unread = 1")[0][0]


def chats(limit: int) -> list[dict[str, Any]]:
    rows = query(
        """SELECT c.id AS chat_id, c.type, c.title, c.username,
             (SELECT COUNT(*) FROM messages WHERE chat_id = c.id AND unread = 1) AS unread,
             (SELECT MAX(date) FROM messages WHERE chat_id = c.id) AS last_date,
             (SELECT substr(text, 1, 100) FROM messages WHERE chat_id = c.id
              ORDER BY date DESC, message_id DESC LIMIT 1) AS last_text
           FROM chats c ORDER BY last_date DESC LIMIT ?""",
        (limit,),
    )
    return [{k: r[k] for k in r.keys() if r[k] not in (None, "")} for r in rows]


def history(chat_id: int, limit: int) -> list[dict[str, Any]]:
    """Last `limit` messages of a chat, oldest first; marks the chat read."""
    rows = query(
        "SELECT * FROM messages WHERE chat_id = ? ORDER BY date DESC, message_id DESC LIMIT ?", (chat_id, limit)
    )
    db().execute("UPDATE messages SET unread = 0 WHERE chat_id = ?", (chat_id,))
    return [row(r) for r in reversed(rows)]


def search(text: str, chat_id: int | None, limit: int) -> list[dict[str, Any]]:
    rows = query(
        "SELECT * FROM messages WHERE instr(fa(text), :q) > 0 AND (:chat IS NULL OR chat_id = :chat)"
        " ORDER BY date DESC, message_id DESC LIMIT :limit",
        {"q": fa(text), "chat": chat_id, "limit": limit},
    )
    return [row(r) for r in rows]
