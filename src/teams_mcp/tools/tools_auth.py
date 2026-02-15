from __future__ import annotations

import time
from typing import Any, Dict

from ..auth.device_code import device_code_poll, device_code_start
from ..auth.scopes import DEFAULT_SCOPES
from ..auth.token_store import TokenBundle, TokenStore
from ..rpc.types import Json, ToolDef, text_content


_store = TokenStore()


async def tool_device_code_start(args: Json) -> Json:
    scopes = args.get("scopes") or DEFAULT_SCOPES
    if isinstance(scopes, str):
        scopes = [scopes]
    payload = await device_code_start([str(s) for s in scopes])
    # return instructions (client copies code + visits URL)
    lines = [
        "Sign in to Microsoft:",
        f"- Visit: {payload.get('verification_uri')}",
        f"- Code: {payload.get('user_code')}",
        f"- Expires in: {payload.get('expires_in')}s",
        "",
        "Then call teams.auth.device_code_poll with the device_code.",
    ]
    return {"content": [{"type": "text", "text": "\n".join(lines)}], "device_code": payload.get("device_code")}


async def tool_device_code_poll(args: Json) -> Json:
    device_code = str(args.get("device_code", "")).strip()
    if not device_code:
        return text_content("Provide device_code.")

    result = await device_code_poll(device_code)
    if "access_token" not in result:
        # still pending or error
        return text_content(f"Auth pending: {result.get('error')} {result.get('error_description','')}".strip())

    expires_in = int(result.get("expires_in", 3600))
    bundle = TokenBundle(
        access_token=result["access_token"],
        refresh_token=result.get("refresh_token"),
        expires_at=int(time.time()) + expires_in,
        id_token=result.get("id_token"),
        account_upn=None,  # optional: you can parse id_token later if needed
    )
    _store.save(bundle)
    return text_content("✅ Auth complete. Token saved.")


async def tool_status(_: Json) -> Json:
    b = _store.load()
    if not b:
        return text_content("Not authenticated.")
    return text_content("Authenticated (token present).")


async def tool_logout(_: Json) -> Json:
    _store.clear()
    return text_content("Logged out (token cleared).")


TOOLS = [
    ToolDef(
        name="teams.auth.device_code_start",
        description="Start Microsoft login via device code flow.",
        input_schema={
            "type": "object",
            "properties": {"scopes": {"type": "array", "items": {"type": "string"}}},
        },
        handler=tool_device_code_start,
    ),
    ToolDef(
        name="teams.auth.device_code_poll",
        description="Poll device code flow until access token is issued.",
        input_schema={
            "type": "object",
            "properties": {"device_code": {"type": "string"}},
            "required": ["device_code"],
        },
        handler=tool_device_code_poll,
    ),
    ToolDef(
        name="teams.auth.status",
        description="Check whether Teams MCP is authenticated.",
        input_schema={"type": "object", "properties": {}},
        handler=tool_status,
    ),
    ToolDef(
        name="teams.auth.logout",
        description="Clear stored tokens.",
        input_schema={"type": "object", "properties": {}},
        handler=tool_logout,
    ),
]
