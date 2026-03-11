from __future__ import annotations

import re
from urllib.parse import unquote

from ..auth.token_store import TokenStore
from ..graph.client import GraphClient
from ..rpc.types import Json, ToolDef, text_content


def _get_store() -> TokenStore:
    global _store
    if _store is None:
        _store = TokenStore()
    return _store

def _get_graph() -> GraphClient:
    global _graph
    if _graph is None:
        _graph = GraphClient(_get_store())
    return _graph

_store: TokenStore | None = None
_graph: GraphClient | None = None


def _parse_thread_id(join_url: str) -> str | None:
    """Extract the chat thread ID from a Teams meeting join URL.

    Teams join links look like:
      https://teams.microsoft.com/l/meetup-join/19%3ameeting_abc123%40thread.v2/...

    The chat thread ID is the URL-decoded segment between ``meetup-join/`` and the next ``/``.
    """
    m = re.search(r"meetup-join/([^/]+)", join_url)
    if m:
        return unquote(m.group(1))
    return None


async def tool_meeting_chat_resolve(args: Json) -> Json:
    """Resolve a Teams join URL to a meeting chat thread ID."""
    join_url = str(args.get("join_url", "")).strip()
    if not join_url:
        return text_content("Provide join_url.")

    thread_id = _parse_thread_id(join_url)
    if thread_id:
        return text_content(f"Resolved chat thread ID: {thread_id}")

    # Fallback: list recent meeting-type chats
    data = await _get_graph().get("/chats", params={"$top": "20", "$filter": "chatType eq 'meeting'"})
    items = data.get("value", [])
    if not items:
        return text_content("Could not parse thread ID from URL, and no recent meeting chats found.")
    lines = ["Could not parse thread ID from URL. Recent meeting chats:"]
    for c in items:
        lines.append(f"- {c.get('id')} | {c.get('topic') or '(no topic)'}")
    return text_content("\n".join(lines))


async def tool_meeting_chat_read(args: Json) -> Json:
    """Read the latest messages from a meeting chat."""
    chat_id = str(args.get("chat_id", "")).strip()
    if not chat_id:
        return text_content("Provide chat_id.")
    top = int(args.get("top", 25) or 25)
    top = max(1, min(top, 50))

    data = await _get_graph().get(f"/chats/{chat_id}/messages", params={"$top": str(top)})
    items = data.get("value", [])
    if not items:
        return text_content("No messages found in this chat.")

    # Return in chronological order (API returns newest first)
    items.reverse()
    lines = [f"Meeting chat messages ({len(items)}):"]
    for msg in items:
        sender = msg.get("from", {})
        user = sender.get("user", {}) if sender else {}
        name = user.get("displayName", "Unknown") if user else "System"
        ts = msg.get("createdDateTime", "")
        body = msg.get("body", {}).get("content", "")
        msg_type = msg.get("messageType", "")
        if msg_type == "systemEventMessage":
            lines.append(f"  [{ts}] [system] {body}")
        else:
            lines.append(f"  [{ts}] {name}: {body}")
    return text_content("\n".join(lines))


async def tool_meeting_chat_post(args: Json) -> Json:
    """Post a message to a meeting chat."""
    chat_id = str(args.get("chat_id", "")).strip()
    text = str(args.get("text", "")).strip()
    if not chat_id or not text:
        return text_content("Provide chat_id and text.")

    body = {"body": {"contentType": "text", "content": text}}
    await _get_graph().post(f"/chats/{chat_id}/messages", body)
    return text_content("Message posted to meeting chat.")


async def tool_meeting_chat_members(args: Json) -> Json:
    """List participants of a meeting chat."""
    chat_id = str(args.get("chat_id", "")).strip()
    if not chat_id:
        return text_content("Provide chat_id.")

    data = await _get_graph().get(f"/chats/{chat_id}/members")
    items = data.get("value", [])
    if not items:
        return text_content("No members found.")

    lines = [f"Meeting chat members ({len(items)}):"]
    for m in items:
        name = m.get("displayName", "Unknown")
        email = m.get("email", "")
        roles = ", ".join(m.get("roles", [])) or "member"
        lines.append(f"- {name} | {email} | {roles}")
    return text_content("\n".join(lines))


TOOLS = [
    ToolDef(
        name="teams.meeting_chat.resolve",
        description="Parse a Teams join URL to extract the meeting chat thread ID. Falls back to listing recent meeting chats.",
        input_schema={
            "type": "object",
            "properties": {"join_url": {"type": "string", "description": "Teams meeting join URL"}},
            "required": ["join_url"],
        },
        handler=tool_meeting_chat_resolve,
    ),
    ToolDef(
        name="teams.meeting_chat.read",
        description="Read the latest messages from a meeting chat.",
        input_schema={
            "type": "object",
            "properties": {
                "chat_id": {"type": "string", "description": "Meeting chat thread ID"},
                "top": {"type": "integer", "default": 25, "description": "Number of messages to return (max 50)"},
            },
            "required": ["chat_id"],
        },
        handler=tool_meeting_chat_read,
    ),
    ToolDef(
        name="teams.meeting_chat.post",
        description="Post a message to a meeting chat.",
        input_schema={
            "type": "object",
            "properties": {
                "chat_id": {"type": "string", "description": "Meeting chat thread ID"},
                "text": {"type": "string", "description": "Message text to post"},
            },
            "required": ["chat_id", "text"],
        },
        handler=tool_meeting_chat_post,
    ),
    ToolDef(
        name="teams.meeting_chat.members",
        description="List participants of a meeting chat with display name, email, and roles.",
        input_schema={
            "type": "object",
            "properties": {"chat_id": {"type": "string", "description": "Meeting chat thread ID"}},
            "required": ["chat_id"],
        },
        handler=tool_meeting_chat_members,
    ),
]
