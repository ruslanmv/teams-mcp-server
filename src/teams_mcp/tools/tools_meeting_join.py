from __future__ import annotations

import re
import time
from typing import Any, Dict
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

# In-process session registry — lost on server restart (stateless by design).
_sessions: Dict[str, Dict[str, Any]] = {}


def _parse_join_url(join_url: str) -> Dict[str, Any]:
    """Extract thread ID and metadata from a Teams join URL."""
    parsed: Dict[str, Any] = {"raw_url": join_url, "thread_id": None}
    m = re.search(r"meetup-join/([^/]+)", join_url)
    if m:
        parsed["thread_id"] = unquote(m.group(1))
    return parsed


def _new_session_id() -> str:
    return f"session-{int(time.time() * 1000)}"


async def tool_meeting_connect(args: Json) -> Json:
    """Connect to a Teams meeting: parse join URL, resolve chat, create session."""
    join_url = str(args.get("join_url", "")).strip()
    if not join_url:
        return text_content("Provide join_url.")

    room_id = str(args.get("room_id", "")).strip() or None
    parsed = _parse_join_url(join_url)
    thread_id = parsed.get("thread_id")

    if not thread_id:
        return text_content("Could not extract thread ID from join URL.")

    # Verify the chat is accessible via Graph API
    try:
        await _get_graph().get(f"/chats/{thread_id}")
    except Exception as exc:
        return text_content(
            f"Chat thread {thread_id} is not accessible. "
            f"Ensure you have joined the meeting and have ChatMessage.Read permission. "
            f"Error: {exc}"
        )

    session_id = _new_session_id()
    session = {
        "session_id": session_id,
        "join_url": join_url,
        "chat_id": thread_id,
        "room_id": room_id,
        "status": "connected",
        "connected_at": time.time(),
        "last_poll_at": None,
        "messages_ingested": 0,
        "voice_enabled": False,
        "parsed": parsed,
    }
    _sessions[session_id] = session

    return text_content(
        f"Connected to meeting.\n"
        f"  session_id: {session_id}\n"
        f"  chat_id: {thread_id}\n"
        f"  room_id: {room_id or '(none)'}\n"
        f"  status: connected"
    )


async def tool_meeting_status(args: Json) -> Json:
    """Return session info. Omit session_id to list all active sessions."""
    session_id = str(args.get("session_id", "")).strip() or None

    if session_id:
        s = _sessions.get(session_id)
        if not s:
            return text_content(f"Session {session_id} not found.")
        lines = [
            f"Session: {s['session_id']}",
            f"  status: {s['status']}",
            f"  chat_id: {s['chat_id']}",
            f"  room_id: {s.get('room_id') or '(none)'}",
            f"  messages_ingested: {s['messages_ingested']}",
            f"  voice_enabled: {s['voice_enabled']}",
            f"  connected_at: {s['connected_at']}",
            f"  last_poll_at: {s.get('last_poll_at')}",
        ]
        return text_content("\n".join(lines))

    # List all sessions
    if not _sessions:
        return text_content("No active sessions.")
    lines = [f"Active sessions ({len(_sessions)}):"]
    for sid, s in _sessions.items():
        lines.append(f"- {sid} | {s['status']} | chat={s['chat_id']} | msgs={s['messages_ingested']}")
    return text_content("\n".join(lines))


async def tool_meeting_disconnect(args: Json) -> Json:
    """Disconnect and remove a meeting session."""
    session_id = str(args.get("session_id", "")).strip()
    if not session_id:
        return text_content("Provide session_id.")

    s = _sessions.pop(session_id, None)
    if not s:
        return text_content(f"Session {session_id} not found.")

    s["status"] = "disconnected"
    return text_content(f"Session {session_id} disconnected and removed.")


TOOLS = [
    ToolDef(
        name="teams.meeting.connect",
        description="Connect to a Teams meeting by join URL. Parses the URL, verifies chat access, and creates a tracked session.",
        input_schema={
            "type": "object",
            "properties": {
                "join_url": {"type": "string", "description": "Teams meeting join URL"},
                "room_id": {"type": "string", "description": "Optional HomePilot room ID to bind this session to"},
            },
            "required": ["join_url"],
        },
        handler=tool_meeting_connect,
    ),
    ToolDef(
        name="teams.meeting.status",
        description="Return session info. Omit session_id to list all active sessions.",
        input_schema={
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Session ID to query. Omit to list all."},
            },
        },
        handler=tool_meeting_status,
    ),
    ToolDef(
        name="teams.meeting.disconnect",
        description="Disconnect and remove a meeting session from the registry.",
        input_schema={
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Session ID to disconnect"},
            },
            "required": ["session_id"],
        },
        handler=tool_meeting_disconnect,
    ),
]
