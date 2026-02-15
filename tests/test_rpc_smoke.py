import pytest
from fastapi.testclient import TestClient

from teams_mcp.main import app


def test_tools_list_smoke():
    c = TestClient(app)
    r = c.post("/rpc", json={"id": 1, "method": "tools/list", "params": {}})
    assert r.status_code == 200
    data = r.json()
    assert "result" in data
    assert isinstance(data["result"], list)
