from __future__ import annotations

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


async def tool_list_chats(args: Json) -> Json:
    top = int(args.get("top", 10) or 10)
    top = max(1, min(top, 50))
    data = await _get_graph().get("/chats", params={"$top": str(top)})
    items = data.get("value", [])
    lines = [f"Recent chats ({len(items)}):"]
    for c in items:
        lines.append(f"- {c.get('id')} | {c.get('topic') or '(no topic)'} | {c.get('chatType')}")
    return text_content("\n".join(lines))


async def tool_send_chat_message(args: Json) -> Json:
    chat_id = str(args.get("chat_id", "")).strip()
    text = str(args.get("text", "")).strip()
    if not chat_id or not text:
        return text_content("Provide chat_id and text.")
    body = {"body": {"contentType": "text", "content": text}}
    await _get_graph().post(f"/chats/{chat_id}/messages", body)
    return text_content("✅ Message sent.")


async def tool_list_joined_teams(_: Json) -> Json:
    data = await _get_graph().get("/me/joinedTeams")
    items = data.get("value", [])
    lines = [f"Joined teams ({len(items)}):"]
    for t in items:
        lines.append(f"- {t.get('id')} | {t.get('displayName')}")
    return text_content("\n".join(lines))


async def tool_list_channels(args: Json) -> Json:
    team_id = str(args.get("team_id", "")).strip()
    if not team_id:
        return text_content("Provide team_id.")
    data = await _get_graph().get(f"/teams/{team_id}/channels")
    items = data.get("value", [])
    lines = [f"Channels ({len(items)}):"]
    for ch in items:
        lines.append(f"- {ch.get('id')} | {ch.get('displayName')}")
    return text_content("\n".join(lines))


async def tool_send_channel_message(args: Json) -> Json:
    team_id = str(args.get("team_id", "")).strip()
    channel_id = str(args.get("channel_id", "")).strip()
    text = str(args.get("text", "")).strip()
    if not team_id or not channel_id or not text:
        return text_content("Provide team_id, channel_id, text.")
    body = {"body": {"contentType": "text", "content": text}}
    await _get_graph().post(f"/teams/{team_id}/channels/{channel_id}/messages", body)
    return text_content("✅ Channel message sent.")


TOOLS = [
    ToolDef(
        name="teams.chats.list_recent",
        description="List recent Teams chats.",
        input_schema={"type": "object", "properties": {"top": {"type": "integer", "default": 10}}},
        handler=tool_list_chats,
    ),
    ToolDef(
        name="teams.chats.send_message",
        description="Send a message to a Teams chat by chat_id.",
        input_schema={
            "type": "object",
            "properties": {"chat_id": {"type": "string"}, "text": {"type": "string"}},
            "required": ["chat_id", "text"],
        },
        handler=tool_send_chat_message,
    ),
    ToolDef(
        name="teams.teams.list_joined",
        description="List teams the authenticated user has joined.",
        input_schema={"type": "object", "properties": {}},
        handler=tool_list_joined_teams,
    ),
    ToolDef(
        name="teams.channels.list",
        description="List channels for a given team_id.",
        input_schema={
            "type": "object",
            "properties": {"team_id": {"type": "string"}},
            "required": ["team_id"],
        },
        handler=tool_list_channels,
    ),
    ToolDef(
        name="teams.channels.send_message",
        description="Send a message to a channel in a team.",
        input_schema={
            "type": "object",
            "properties": {"team_id": {"type": "string"}, "channel_id": {"type": "string"}, "text": {"type": "string"}},
            "required": ["team_id", "channel_id", "text"],
        },
        handler=tool_send_channel_message,
    ),
]
