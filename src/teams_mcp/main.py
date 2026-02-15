from __future__ import annotations

import uvicorn

from .config import settings
from .logging import setup_logging
from .rpc.server import create_mcp_app
from .tools import ALL_TOOLS

setup_logging()

app = create_mcp_app(server_name="teams-mcp-server", tools=ALL_TOOLS)


def run() -> None:
    uvicorn.run(app, host=settings.host, port=settings.port, log_level=settings.log_level.lower())
