"""MCP tools for Azure Communication Services (ACS) meeting audio.

Provides tools to join a Teams meeting as an ACS bot participant,
check session status, and leave the meeting.  Actual audio capture
is a scaffold (see ``acs/client.py`` for implementation notes).

Tools:
    - ``teams.acs.join``       — Join a meeting via ACS for audio capture
    - ``teams.acs.status``     — Check ACS session status
    - ``teams.acs.leave``      — Leave an ACS meeting session
"""
from __future__ import annotations

from ..acs.client import acs_join, acs_leave, acs_status
from ..rpc.types import Json, ToolDef, text_content


async def tool_acs_join(args: Json) -> Json:
    """Join a Teams meeting via ACS for real-time audio capture."""
    join_url = args.get("join_url", "")
    connection_string = args.get("connection_string", "")

    if not join_url:
        return text_content("Error: 'join_url' is required.")
    if not connection_string:
        return text_content(
            "Error: 'connection_string' is required.  "
            "Provide your ACS resource connection string from Azure Portal."
        )

    session = await acs_join(join_url=join_url, connection_string=connection_string)

    if session.error:
        return text_content(f"ACS join failed: {session.error}")

    lines = [
        f"ACS session created: {session.session_id}",
        f"  status: {session.status}",
        f"  join_url: {join_url[:80]}...",
        "",
        "Note: Full audio capture requires azure-communication-calling SDK.",
        "Session is in 'pending_sdk' state — config validated, awaiting SDK wiring.",
    ]
    return text_content("\n".join(lines))


async def tool_acs_status(args: Json) -> Json:
    """Check ACS session status."""
    session_id = args.get("session_id")
    sessions = await acs_status(session_id)

    if not sessions:
        if session_id:
            return text_content(f"ACS session '{session_id}' not found.")
        return text_content("No ACS sessions active.")

    lines = [f"ACS sessions ({len(sessions)}):"]
    for s in sessions:
        lines.append(f"  [{s['session_id']}]  status={s['status']}  "
                      f"audio_chunks={s['audio_chunks_captured']}  "
                      f"transcripts={s['transcripts_count']}")
        if s.get("error"):
            lines.append(f"    error: {s['error']}")
    return text_content("\n".join(lines))


async def tool_acs_leave(args: Json) -> Json:
    """Leave an ACS meeting session."""
    session_id = args.get("session_id", "")
    if not session_id:
        return text_content("Error: 'session_id' is required.")

    session = await acs_leave(session_id)
    if not session:
        return text_content(f"ACS session '{session_id}' not found.")

    return text_content(f"ACS session '{session_id}' disconnected.")


TOOLS = [
    ToolDef(
        name="teams.acs.join",
        description=(
            "Join a Teams meeting via Azure Communication Services for real-time audio capture. "
            "Requires an ACS connection string from Azure Portal. "
            "Currently a scaffold — full audio capture requires azure-communication-calling SDK."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "join_url": {
                    "type": "string",
                    "description": "Teams meeting join URL",
                },
                "connection_string": {
                    "type": "string",
                    "description": "ACS resource connection string (endpoint=https://...;accesskey=...)",
                },
            },
            "required": ["join_url", "connection_string"],
        },
        handler=tool_acs_join,
    ),
    ToolDef(
        name="teams.acs.status",
        description="Check ACS session status. Omit session_id to list all active sessions.",
        input_schema={
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "ACS session ID (omit to list all)",
                },
            },
        },
        handler=tool_acs_status,
    ),
    ToolDef(
        name="teams.acs.leave",
        description="Leave an ACS meeting session and stop audio capture.",
        input_schema={
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "ACS session ID to disconnect",
                },
            },
            "required": ["session_id"],
        },
        handler=tool_acs_leave,
    ),
]
