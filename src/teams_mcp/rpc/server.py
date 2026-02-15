from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .types import Json, ToolDef, error_content

log = logging.getLogger("teams_mcp.rpc")


def create_mcp_app(server_name: str, tools: List[ToolDef]) -> FastAPI:
    app = FastAPI(title=server_name)

    tool_map = {t.name: t for t in tools}

    @app.get("/health")
    async def health() -> Json:
        return {"ok": True, "server": server_name, "tools": list(tool_map.keys())}

    @app.post("/rpc")
    async def rpc(req: Request) -> JSONResponse:
        body = await req.json()
        method = body.get("method")
        params = body.get("params") or {}
        rpc_id = body.get("id")

        try:
            if method == "tools/list":
                return JSONResponse(
                    {
                        "id": rpc_id,
                        "result": [
                            {
                                "name": t.name,
                                "description": t.description,
                                "inputSchema": t.input_schema,
                            }
                            for t in tools
                        ],
                    }
                )

            if method == "tools/call":
                name = params.get("name")
                args = params.get("arguments") or {}
                if name not in tool_map:
                    return JSONResponse({"id": rpc_id, "result": error_content(f"Unknown tool: {name}")})
                tool = tool_map[name]
                out = await tool.handler(args)
                return JSONResponse({"id": rpc_id, "result": out})

            return JSONResponse({"id": rpc_id, "result": error_content(f"Unknown method: {method}")})
        except Exception as e:
            log.exception("RPC failure")
            return JSONResponse({"id": rpc_id, "result": error_content(str(e))})

    return app
