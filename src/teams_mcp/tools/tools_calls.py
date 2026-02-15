from __future__ import annotations

from ..rpc.types import Json, ToolDef, text_content


async def tool_join_meeting(args: Json) -> Json:
    """
    Real "join a Teams call as a participant" requires:
    - Azure Bot registration + Bot Framework / Graph Communications API (cloud)
    - or ACS Calling + Teams interop (still requires Azure setup)
    This MCP tool is intentionally scaffolded so you can implement it later
    without changing the tool surface.
    """
    meeting_join_url = str(args.get("meeting_join_url", "")).strip()
    if not meeting_join_url:
        return text_content("Provide meeting_join_url.")

    return text_content(
        "Call-join is scaffolded but not enabled yet.\n"
        "To implement real participation: add a Bot Framework/Graph Calling backend and "
        "wire this tool to instruct that bot to join the meeting.\n"
        f"Join URL received:\n{meeting_join_url}"
    )


TOOLS = [
    ToolDef(
        name="teams.calls.join_meeting",
        description="(Scaffold) Join a Teams meeting as a bot participant (requires Azure bot/calling infra).",
        input_schema={
            "type": "object",
            "properties": {"meeting_join_url": {"type": "string"}},
            "required": ["meeting_join_url"],
        },
        handler=tool_join_meeting,
    ),
]
