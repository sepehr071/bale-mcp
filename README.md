<!-- mcp-name: io.github.sepehr071/bale-mcp -->

<div align="center">

# 💬 bale-mcp

**Talk to your AI agents on Bale, privately.**<br>
Let Claude, Cursor or Copilot read what people send your Bale bot, keep a searchable history,<br>
reply, send files, and ask you a question and wait for your tap, all from your own machine.

[![PyPI](https://img.shields.io/pypi/v/bale-mcp?color=2563eb)](https://pypi.org/project/bale-mcp/)
[![Python](https://img.shields.io/pypi/pyversions/bale-mcp)](https://pypi.org/project/bale-mcp/)
[![CI](https://github.com/sepehr071/bale-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/sepehr071/bale-mcp/actions/workflows/ci.yml)
[![MCP Registry](https://img.shields.io/badge/MCP_Registry-io.github.sepehr071%2Fbale--mcp-7c3aed)](https://registry.modelcontextprotocol.io/v0/servers?search=bale-mcp)
[![License: MIT](https://img.shields.io/badge/license-MIT-16a34a)](https://github.com/sepehr071/bale-mcp/blob/main/LICENSE)

[![Install in Cursor](https://cursor.com/deeplink/mcp-install-dark.svg)](https://cursor.com/en/install-mcp?name=bale&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyJiYWxlLW1jcCJdLCJlbnYiOnsiQkFMRV9CT1RfVE9LRU4iOiJ5b3VyLWJvdC10b2tlbiIsIkJBTEVfQUxMT1dFRF9DSEFUUyI6InlvdXItY2hhdC1pZCJ9fQ==)
[![Install in VS Code](https://img.shields.io/badge/VS_Code-Install_bale--mcp-0098FF?style=flat-square&logo=visualstudiocode&logoColor=white)](https://vscode.dev/redirect/mcp/install?name=bale&config=%7B%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22bale-mcp%22%5D%2C%22env%22%3A%7B%22BALE_BOT_TOKEN%22%3A%22your-bot-token%22%2C%22BALE_ALLOWED_CHATS%22%3A%22your-chat-id%22%7D%7D)

[Quick start](#quick-start) · [What it can do](#what-it-can-do) · [Privacy](#privacy-and-security) · [Tools](#tools) · [FAQ](#faq) · [فارسی](#فارسی)

</div>

---

## Why

Agents now run for minutes or hours: deploys, data jobs, research. You want them to tell you when they are done,
ask before they do something risky, and take new instructions while you are away from the keyboard. For many
people in Iran that phone is running [Bale (بله)](https://bale.ai). With `bale-mcp` the agent does it through
your own Bale bot:

> **You:** Run the migration on staging, but ask me on Bale before you touch the users table.
>
> **Agent:** *calls* `bot_send_message(chat_id=…, text="Migration step 3 alters users (2.1M rows). Go?", buttons=[["Go", "Stop"]])` → `bot_wait_for_reply(chat_id=…, after_message_id=3)`
>
> *(you tap **Go** on your phone)*
>
> ```json
> {"messages": [{"kind": "button", "text": "Go", "from": "Sepehr", "message_id": 3}], "timed_out": false}
> ```
>
> **Agent:** Got your approval. Running step 3 now; I'll message you when it's done.

<sub>The tool calls are real; the reply shape is from a live test against tapi.bale.ai on 2026-10-03.</sub>

## What it can do

- 📥 **Read** what people send your bot, from every chat, with sender, kind and chat id
- 🗂️ **Keep a history**: the Bot API forgets messages after 24 hours; `bale-mcp` keeps them in a local SQLite file
- 🔎 **Search** that history, Persian-aware: Arabic and Persian ی/ک, Persian and Latin digits and ZWNJ all match
- 🙋 **Ask and wait**: send a question with inline buttons, then block until you answer or tap
- 📤 **Send** text (Markdown), photos, documents, video, audio and voice; edit and delete the bot's messages
- 📎 **Download** files people send (receipts, voice notes, documents) to your computer
- 🔒 **Private by design**: runs on your machine, talks only to Bale, no telemetry, optional chat allowlist

## Quick start

You need [uv](https://docs.astral.sh/uv/getting-started/installation/) and a Bale bot.

1. **Create a bot.** In Bale open [@botfather](https://ble.ir/botfather), tap «ساخت بازوی جدید» (new bot), pick a
   name and a username ending in `bot`, and copy the token.
2. **Add the server** to your MCP client (below).
3. **Find your chat id.** Send `/start` to your bot, then ask the agent: *"Check my new Bale messages."* The
   `chat_id` it shows is yours. Put it in `BALE_ALLOWED_CHATS` so the bot ignores everyone else.

<details open>
<summary><b>Claude Code</b></summary>

```bash
claude mcp add bale -e BALE_BOT_TOKEN=123456789:your-token -e BALE_ALLOWED_CHATS=your-chat-id -- uvx bale-mcp
```
</details>

<details>
<summary><b>Claude Desktop</b></summary>

Settings → Developer → Edit Config, then add:

```json
{
  "mcpServers": {
    "bale": {
      "command": "uvx",
      "args": ["bale-mcp"],
      "env": {
        "BALE_BOT_TOKEN": "123456789:your-token",
        "BALE_ALLOWED_CHATS": "your-chat-id"
      }
    }
  }
}
```
</details>

<details>
<summary><b>Cursor</b></summary>

Click **Install in Cursor** above and fill in the two values, or add the Claude Desktop block to `~/.cursor/mcp.json`.
</details>

<details>
<summary><b>VS Code (Copilot agent mode)</b></summary>

Add to `.vscode/mcp.json`. VS Code asks for the token once and stores it securely:

```json
{
  "inputs": [
    { "type": "promptString", "id": "bale-token", "description": "Bale bot token", "password": true }
  ],
  "servers": {
    "bale": {
      "type": "stdio",
      "command": "uvx",
      "args": ["bale-mcp"],
      "env": { "BALE_BOT_TOKEN": "${input:bale-token}", "BALE_ALLOWED_CHATS": "your-chat-id" }
    }
  }
}
```
</details>

<details>
<summary><b>Anything else</b></summary>

It's a standard stdio MCP server: run `uvx bale-mcp`, or `pip install bale-mcp` and run `bale-mcp`, with
`BALE_BOT_TOKEN` in the environment.
</details>

Then just ask:

- "When the test suite finishes, send me the summary on Bale."
- "Any new messages on Bale? Summarize them and draft replies, but ask me before sending."
- "Ask me on Bale whether to deploy, with Yes/No buttons, and wait for my answer."
- "Find the invoice photo someone sent the bot last week and save it to my Downloads."
- <span dir="rtl">پیام&zwnj;های جدید بله را بخوان و خلاصه&zwnj;شان را بگو.</span>

## How it works

```text
  AI agent  (Claude, Cursor, Copilot, ...)
      │
      │  MCP over stdio
      ▼
  bale-mcp  (runs on your machine)  ──▶  ~/.bale-mcp/messages.db   local history (SQLite)
      │
      │  HTTPS, official Bot API
      ▼
  tapi.bale.ai  ◀──▶  your Bale app
```

Each reading tool first pulls pending updates from Bale (`getUpdates`) into the local store, then answers from
it. Sent messages are stored too, so a chat's history shows both sides.

## Privacy and security

- **Local only.** `bale-mcp` runs on your machine. The only host it talks to is `tapi.bale.ai`. There is no relay
  server, no telemetry and no analytics.
- **Your history stays on your disk.** Messages are kept in `~/.bale-mcp/messages.db` (the folder is user-only on
  macOS/Linux). Set `BALE_MCP_DB=:memory:` to keep nothing on disk, or delete the file at any time.
- **Allowlist.** With `BALE_ALLOWED_CHATS` set, messages from any other chat are dropped before they are stored or
  shown to the agent, so a stranger who finds your bot cannot feed your agent instructions. The server also
  refuses to send to any other chat.
- **Prompt-injection aware.** The server tells the agent that message text is data from other people, never
  instructions to follow.
- **Confirm before sending.** Tools that change something (send, edit, delete) are annotated `destructiveHint`, and
  their descriptions tell the agent to confirm the recipient and content with you first.
- **The token never leaks.** It never appears in tool output, errors or logs.
- **Know the limits.** Bale has no end-to-end encryption: Bale's servers see what goes through your bot, as with any
  Bale chat. `bale-mcp` adds no other party.

## Tools

Chat ids are numbers (they can exceed 32 bits), or `@username` for public channels and groups when sending.

<details open>
<summary><b>📥 Read</b> (6)</summary>

| Tool | What it does |
|---|---|
| `bot_get_new_messages` | Messages people sent the bot since the last check, from every chat, oldest first |
| `bot_list_chats` | Chats the bot has talked in, with unread count and last message |
| `bot_read_chat` | A chat's recent history in both directions |
| `bot_search_messages` | Search the stored history; Persian-aware |
| `bot_wait_for_reply` | Wait until someone writes in a chat or taps a button (up to 10 minutes) |
| `bot_download_file` | Save a photo, document, voice note, ... to this computer (max 20 MB) |
</details>

<details open>
<summary><b>📤 Send</b> (4)</summary>

| Tool | What it does |
|---|---|
| `bot_send_message` | Send text, optionally as a reply and with inline buttons |
| `bot_send_file` | Send a photo, document, video, audio or voice file by URL or local path (max 50 MB) |
| `bot_edit_message` | Replace the text of a message the bot sent |
| `bot_delete_message` | Delete a message |
</details>

<details open>
<summary><b>🔧 Bot</b> (3)</summary>

| Tool | What it does |
|---|---|
| `bot_get_me` | Check the token: bot id, username, name |
| `bot_get_chat` | A chat's type, title or name, username and description |
| `bot_get_webhook_info` | Whether a webhook is set, pending updates and the last error |
</details>

## Good to know

- **Someone must message the bot first.** A user has to send `/start` before the bot can message them; in groups and
  channels the bot must be a member.
- **History starts when `bale-mcp` first reads.** Bale keeps undelivered updates for 24 hours (the last 2000), so
  anything older than that, or read by another program, is gone.
- **One reader per bot.** Webhooks block `getUpdates`, and two programs polling the same token steal each other's
  updates. `bot_get_webhook_info` shows a webhook. Several `bale-mcp` processes may share one `BALE_MCP_DB`.
- **Text is Markdown.** Bale formats every message: `*bold*`, `_italic_`.
- **Button presses** come back as messages of kind `button` whose text is the label (cut to 64 bytes).

## FAQ

<details>
<summary><b>Can it read my personal chats?</b></summary>

No. It uses the official Bot API, so it only sees what people send to your bot, and messages in groups and channels
the bot is a member of. It cannot log in as you.
</details>

<details>
<summary><b>Do I need an Iranian IP?</b></summary>

No: in testing `tapi.bale.ai` answered from a foreign (Turkish) exit. If every call fails with "Could not reach
tapi.bale.ai", set `BALE_MCP_PROXY` to an HTTP proxy that can reach it. Normal system proxy variables are ignored on purpose.
</details>

<details>
<summary><b>The tools say "Bale rejected the bot token"</b></summary>

The token is wrong or was revoked. Copy it again from @botfather. (Bale answers a bad token with HTTP 403 or 404.)
</details>

<details>
<summary><b>The agent waited and timed out</b></summary>

`bot_wait_for_reply` returns `timed_out: true` when nobody answered in time; the agent can call it again. Some MCP
clients cancel tool calls after about a minute; use a shorter `timeout_seconds` there.
</details>

<details>
<summary><b>Claude Desktop says <code>uvx</code> is not found</b></summary>

Use the full path to `uvx` (`where uvx` on Windows, `which uvx` on macOS/Linux) as `command`.
</details>

<details>
<summary><b>How do I debug what the agent sees?</b></summary>

```bash
npx @modelcontextprotocol/inspector -e BALE_BOT_TOKEN=123456789:your-token uvx bale-mcp
```
</details>

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `BALE_BOT_TOKEN` | required | Bot token from @botfather |
| `BALE_ALLOWED_CHATS` | unset (all chats) | Comma-separated chat ids or `@usernames`; all other chats are ignored and never messaged |
| `BALE_MCP_DB` | `~/.bale-mcp/messages.db` | Local history file; `:memory:` keeps nothing on disk |
| `BALE_MCP_PROXY` | unset | HTTP proxy for every request, e.g. `http://user:pass@host:port` |

## فارسی

<div dir="rtl">

**bale-mcp** به دستیار هوش مصنوعی شما (Claude، Cursor، Copilot و ...) اجازه می&zwnj;دهد از طریق بازوی (ربات) بله خودتان
پیام&zwnj;ها را بخواند، در آن&zwnj;ها جستجو کند، پاسخ و فایل بفرستد، و از شما سؤال بپرسد و منتظر جوابتان بماند.

- روی سیستم خود شما اجرا می&zwnj;شود و جز سرور بله به هیچ جای دیگری داده نمی&zwnj;فرستد.
- تاریخچه پیام&zwnj;ها فقط روی دیسک خودتان ذخیره می&zwnj;شود (`BALE_MCP_DB=:memory:` یعنی هیچ ذخیره&zwnj;ای).
- با `BALE_ALLOWED_CHATS` فقط چت&zwnj;های شما خوانده می&zwnj;شوند و پیام غریبه&zwnj;ها اصلاً به دستیار نمی&zwnj;رسد.
- جستجو فارسی را می&zwnj;فهمد: «ی/ي»، «ک/ك»، اعداد فارسی و نیم&zwnj;فاصله فرقی نمی&zwnj;کنند.
- بله رمزنگاری سرتاسری ندارد؛ این ابزار طرف سومی اضافه نمی&zwnj;کند.

**نصب در Claude Code:** توکن را از [@botfather](https://ble.ir/botfather) بگیرید و:

</div>

```bash
claude mcp add bale -e BALE_BOT_TOKEN=123456789:your-token -- uvx bale-mcp
```

<div dir="rtl">

بعد به بازوی خود `/start` بفرستید و بپرسید: «پیام&zwnj;های جدید بله را بخوان.»

</div>

## Development

```bash
git clone https://github.com/sepehr071/bale-mcp && cd bale-mcp
uv sync
uv run pytest                 # offline, against a mocked Bot API
uv run pytest -m live         # read-only calls with BALE_BOT_TOKEN
uv run pytest -m live_send    # sends, edits and deletes one message in BALE_TEST_CHAT_ID
uv run ruff check .
```

Tools live in `src/bale_mcp/bot.py` (sending, bot info) and `inbox.py` (reading, waiting, downloads); `store.py`
is the local SQLite history. Each tool is a typed async function with a docstring that tells the agent when to use
it. Issues and PRs are welcome.

Releases: bump the version in `pyproject.toml` and `server.json`, then push a `v*` tag. GitHub Actions tests,
publishes to PyPI and the [MCP Registry](https://registry.modelcontextprotocol.io), and creates the GitHub Release.

## Disclaimer

Unofficial and not affiliated with or endorsed by Bale. It uses Bale's official, public
[Bot API](https://docs.bale.ai/). Follow Bale's terms, and don't use it to spam people.

## License

[MIT](https://github.com/sepehr071/bale-mcp/blob/main/LICENSE)
