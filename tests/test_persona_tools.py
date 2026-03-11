"""
Unit tests for the persona meeting tools.

Tests verify tool registration, schema correctness, and handler logic
that does NOT require a live browser or Playwright (session management,
error handling, argument validation).
"""
import pytest
from fastapi.testclient import TestClient

from teams_mcp.main import app
from teams_mcp.tools import ALL_TOOLS
from teams_mcp.tools.tools_persona import (
    _persona_sessions,
    tool_persona_join,
    tool_persona_leave,
    tool_persona_status,
    tool_persona_set_face,
    tool_persona_speak,
    tool_persona_listen,
    tool_persona_chat_post,
    tool_persona_chat_read,
)


client = TestClient(app)


def _text(result: dict) -> str:
    """Extract text from MCP tool result."""
    return result["content"][0]["text"]


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

class TestPersonaToolRegistration:
    """Verify all persona tools are registered and discoverable."""

    def test_total_tool_count(self):
        """27 existing + 8 persona = 35 total."""
        assert len(ALL_TOOLS) == 35, f"Expected 35 tools, got {len(ALL_TOOLS)}"

    def test_persona_tools_registered(self):
        names = {t.name for t in ALL_TOOLS}
        expected = {
            "teams.persona.join",
            "teams.persona.leave",
            "teams.persona.status",
            "teams.persona.set_face",
            "teams.persona.speak",
            "teams.persona.listen",
            "teams.persona.chat_post",
            "teams.persona.chat_read",
        }
        missing = expected - names
        assert not missing, f"Missing persona tools: {missing}"

    def test_persona_tools_in_rpc_list(self):
        r = client.post("/rpc", json={"id": 1, "method": "tools/list", "params": {}})
        assert r.status_code == 200
        tools = r.json()["result"]
        names = {t["name"] for t in tools}
        assert "teams.persona.join" in names
        assert "teams.persona.speak" in names
        assert "teams.persona.listen" in names

    def test_health_includes_persona_tools(self):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert "teams.persona.join" in data["tools"]
        assert "teams.persona.leave" in data["tools"]


# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------

class TestPersonaSchemas:
    """Verify persona tool input schemas."""

    def _get_tool(self, name: str):
        for t in ALL_TOOLS:
            if t.name == name:
                return t
        pytest.fail(f"Tool {name} not found")

    def test_join_schema(self):
        t = self._get_tool("teams.persona.join")
        props = t.input_schema["properties"]
        assert "join_url" in props
        assert "display_name" in props
        assert "face_image" in props
        assert "tts_voice" in props
        assert "join_url" in t.input_schema["required"]
        assert "display_name" in t.input_schema["required"]

    def test_leave_schema(self):
        t = self._get_tool("teams.persona.leave")
        assert "session_id" in t.input_schema["required"]

    def test_speak_schema(self):
        t = self._get_tool("teams.persona.speak")
        props = t.input_schema["properties"]
        assert "session_id" in props
        assert "text" in props
        assert "voice_model" in props
        assert "session_id" in t.input_schema["required"]
        assert "text" in t.input_schema["required"]

    def test_listen_schema(self):
        t = self._get_tool("teams.persona.listen")
        props = t.input_schema["properties"]
        assert "session_id" in props
        assert "duration_ms" in props

    def test_chat_post_schema(self):
        t = self._get_tool("teams.persona.chat_post")
        assert "session_id" in t.input_schema["required"]
        assert "text" in t.input_schema["required"]

    def test_chat_read_schema(self):
        t = self._get_tool("teams.persona.chat_read")
        props = t.input_schema["properties"]
        assert "session_id" in props
        assert "last_n" in props

    def test_set_face_schema(self):
        t = self._get_tool("teams.persona.set_face")
        assert "session_id" in t.input_schema["required"]
        assert "image_path" in t.input_schema["required"]


# ---------------------------------------------------------------------------
# Handler logic — argument validation (no browser needed)
# ---------------------------------------------------------------------------

class TestPersonaHandlerValidation:
    """Test handler argument validation without launching a browser."""

    @pytest.fixture(autouse=True)
    def _clear_sessions(self):
        _persona_sessions.clear()
        yield
        _persona_sessions.clear()

    async def test_join_missing_url(self):
        result = await tool_persona_join({})
        assert "Error" in _text(result)
        assert "join_url" in _text(result)

    async def test_join_missing_name(self):
        result = await tool_persona_join({"join_url": "https://teams.microsoft.com/l/meetup-join/..."})
        assert "Error" in _text(result)
        assert "display_name" in _text(result)

    async def test_leave_missing_session_id(self):
        result = await tool_persona_leave({})
        assert "Error" in _text(result)
        assert "session_id" in _text(result)

    async def test_leave_unknown_session(self):
        result = await tool_persona_leave({"session_id": "nonexistent"})
        assert "not found" in _text(result)

    async def test_status_no_sessions(self):
        result = await tool_persona_status({})
        assert "No active persona sessions" in _text(result)

    async def test_status_unknown_session(self):
        result = await tool_persona_status({"session_id": "nonexistent"})
        assert "not found" in _text(result)

    async def test_speak_missing_session(self):
        result = await tool_persona_speak({"session_id": "x", "text": "hello"})
        assert "not found" in _text(result)

    async def test_speak_missing_text(self):
        # Fake a session to test text validation
        _persona_sessions["fake"] = {"session_id": "fake", "browser": None, "tts_voice": "en_US-amy-medium"}
        result = await tool_persona_speak({"session_id": "fake"})
        assert "Error" in _text(result)
        assert "text" in _text(result)

    async def test_listen_no_browser(self):
        _persona_sessions["fake"] = {"session_id": "fake", "browser": None}
        result = await tool_persona_listen({"session_id": "fake"})
        assert "Error" in _text(result)
        assert "not active" in _text(result)

    async def test_chat_post_no_browser(self):
        _persona_sessions["fake"] = {"session_id": "fake", "browser": None}
        result = await tool_persona_chat_post({"session_id": "fake", "text": "hi"})
        assert "Error" in _text(result)

    async def test_chat_read_no_browser(self):
        _persona_sessions["fake"] = {"session_id": "fake", "browser": None}
        result = await tool_persona_chat_read({"session_id": "fake"})
        assert "Error" in _text(result)

    async def test_set_face_missing_path(self):
        _persona_sessions["fake"] = {"session_id": "fake"}
        result = await tool_persona_set_face({"session_id": "fake"})
        assert "Error" in _text(result)
        assert "image_path" in _text(result)


# ---------------------------------------------------------------------------
# RPC integration
# ---------------------------------------------------------------------------

class TestPersonaRPC:
    """Test persona tools via JSON-RPC endpoint."""

    def test_persona_join_via_rpc_missing_args(self):
        r = client.post("/rpc", json={
            "id": 1,
            "method": "tools/call",
            "params": {"name": "teams.persona.join", "arguments": {}},
        })
        assert r.status_code == 200
        text = r.json()["result"]["content"][0]["text"]
        assert "Error" in text

    def test_persona_status_via_rpc(self):
        r = client.post("/rpc", json={
            "id": 1,
            "method": "tools/call",
            "params": {"name": "teams.persona.status", "arguments": {}},
        })
        assert r.status_code == 200
        text = r.json()["result"]["content"][0]["text"]
        assert "No active persona sessions" in text

    def test_persona_leave_via_rpc_unknown(self):
        r = client.post("/rpc", json={
            "id": 1,
            "method": "tools/call",
            "params": {"name": "teams.persona.leave", "arguments": {"session_id": "x"}},
        })
        assert r.status_code == 200
        text = r.json()["result"]["content"][0]["text"]
        assert "not found" in text
