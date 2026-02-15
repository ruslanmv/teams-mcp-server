from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional

Json = Dict[str, Any]
ToolHandler = Callable[[Json], Awaitable[Json]]


@dataclass(frozen=True)
class ToolDef:
    name: str
    description: str
    input_schema: Json
    handler: ToolHandler


def text_content(text: str) -> Json:
    return {"content": [{"type": "text", "text": text}]}


def error_content(message: str) -> Json:
    # MCP clients typically surface this as tool error text
    return {"content": [{"type": "text", "text": f"Error: {message}"}]}
