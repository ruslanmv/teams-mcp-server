from __future__ import annotations

from dateutil import parser
from datetime import datetime, timedelta, timezone

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


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


async def tool_list_today(_: Json) -> Json:
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return await tool_list_range({"time_min": _iso(start), "time_max": _iso(end)})


async def tool_list_range(args: Json) -> Json:
    time_min = str(args.get("time_min", "")).strip()
    time_max = str(args.get("time_max", "")).strip()
    if not time_min or not time_max:
        return text_content("Provide time_min and time_max (ISO timestamps).")

    # Graph expects DateTimeTimeZone shape via query for /calendarView
    data = await _get_graph().get(
        "/me/calendarView",
        params={
            "startDateTime": parser.isoparse(time_min).isoformat(),
            "endDateTime": parser.isoparse(time_max).isoformat(),
            "$top": "50",
            "$orderby": "start/dateTime",
        },
    )
    items = data.get("value", [])
    lines = [f"Events ({len(items)}):"]
    for ev in items:
        s = ev.get("start", {}).get("dateTime")
        e = ev.get("end", {}).get("dateTime")
        subj = ev.get("subject") or "(no title)"
        lines.append(f"- {ev.get('id')} | {s} → {e} | {subj}")
    return text_content("\n".join(lines))


async def tool_get_join_link(args: Json) -> Json:
    event_id = str(args.get("event_id", "")).strip()
    if not event_id:
        return text_content("Provide event_id.")
    ev = await _get_graph().get(f"/me/events/{event_id}")
    link = ev.get("onlineMeeting", {}).get("joinUrl") or ev.get("onlineMeetingUrl") or ev.get("webLink")
    if not link:
        return text_content("No join link found on this event.")
    return text_content(f"Join link:\n{link}")


TOOLS = [
    ToolDef(
        name="teams.meetings.list_today",
        description="List today's calendar events (UTC) from Microsoft account.",
        input_schema={"type": "object", "properties": {}},
        handler=tool_list_today,
    ),
    ToolDef(
        name="teams.meetings.list_range",
        description="List events in a time window (ISO time_min/time_max).",
        input_schema={
            "type": "object",
            "properties": {"time_min": {"type": "string"}, "time_max": {"type": "string"}},
            "required": ["time_min", "time_max"],
        },
        handler=tool_list_range,
    ),
    ToolDef(
        name="teams.meetings.get_join_link",
        description="Get join link for an event_id (if online meeting).",
        input_schema={
            "type": "object",
            "properties": {"event_id": {"type": "string"}},
            "required": ["event_id"],
        },
        handler=tool_get_join_link,
    ),
]
