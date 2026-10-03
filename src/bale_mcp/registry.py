"""Collects tool functions from the tool modules; server.py registers them."""

from collections.abc import Callable
from typing import Any

# (function, title, sends): `sends` tools change something outside (message, SMS code, logout).
TOOLS: list[tuple[Callable[..., Any], str, bool]] = []


def tool(title: str, *, sends: bool = False) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Mark an async function as an MCP tool with a human-readable title."""

    def register(fn: Callable[..., Any]) -> Callable[..., Any]:
        TOOLS.append((fn, title, sends))
        return fn

    return register
