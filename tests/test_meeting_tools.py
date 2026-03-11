"""
Unit tests for the meeting chat, meeting join, and voice tools.

These tests verify tool registration, schema correctness, and handler logic
that does NOT require a live Graph API connection (URL parsing, session
lifecycle, voice state management).
"""
import pytest
from fastapi.testclient import TestClient

from teams_mcp.main import app
from teams_mcp.tools import ALL_TOOLS
from teams_mcp.tools.tools_meeting_chat import _parse_thread_id
from teams_mcp.tools.tools_meeting_join import _sessions, tool_meeting_connect, tool_meeting_status, tool_meeting_disconnect
from teams_mcp.tools.tools_voice import get_voice_state, _voice_state


client = TestClient(app)


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

class TestToolRegistration:
    """Verify all new tools are registered and discoverable via RPC."""

    def test_total_tool_count(self):
        assert len(ALL_TOOLS) == 35, f"Expected 35 tools (27 native + 8 persona), got {len(ALL_TOOLS)}"

    def test_new_tools_registered(self):
        names = {t.name for t in ALL_TOOLS}
        expected_new = {
            "teams.meeting_chat.resolve",
            "teams.meeting_chat.read",
            "teams.meeting_chat.post",
            "teams.meeting_chat.members",
            "teams.meeting.connect",
            "teams.meeting.status",
            "teams.meeting.disconnect",
            "teams.voice.toggle",
            "teams.voice.status",
            "teams.voice.configure",
        }
        missing = expected_new - names
        assert not missing, f"Missing tools: {missing}"

    def test_tools_list_rpc(self):
        r = client.post("/rpc", json={"id": 1, "method": "tools/list", "params": {}})
        assert r.status_code == 200
        tools = r.json()["result"]
        names = {t["name"] for t in tools}
        assert "teams.meeting_chat.resolve" in names
        assert "teams.meeting.connect" in names
        assert "teams.voice.toggle" in names

    def test_health_lists_tool_names(self):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert "teams.meeting_chat.resolve" in data["tools"]
        assert "teams.voice.status" in data["tools"]
        assert len(data["tools"]) == 35


# ---------------------------------------------------------------------------
# Meeting chat — URL parsing
# ---------------------------------------------------------------------------

class TestMeetingChatParsing:
    """Test Teams join URL → thread ID extraction."""

    def test_standard_url(self):
        url = "https://teams.microsoft.com/l/meetup-join/19%3ameeting_abc123%40thread.v2/0"
        assert _parse_thread_id(url) == "19:meeting_abc123@thread.v2"

    def test_complex_url(self):
        url = (
            "https://teams.microsoft.com/l/meetup-join/"
            "19%3ameeting_NzQ1MTY2%40thread.v2/"
            "0?context=%7b%22Tid%22%3a%22abc%22%7d"
        )
        assert _parse_thread_id(url) == "19:meeting_NzQ1MTY2@thread.v2"

    def test_no_match(self):
        assert _parse_thread_id("https://example.com/not-a-teams-url") is None

    def test_empty_string(self):
        assert _parse_thread_id("") is None


# ---------------------------------------------------------------------------
# Meeting join — session lifecycle (no Graph API needed)
# ---------------------------------------------------------------------------

class TestMeetingJoinSessions:
    """Test session connect/status/disconnect without Graph API."""

    @pytest.fixture(autouse=True)
    def _clear_sessions(self):
        _sessions.clear()
        yield
        _sessions.clear()

    async def test_status_no_sessions(self):
        result = await tool_meeting_status({})
        assert "No active sessions" in result["content"][0]["text"]

    async def test_status_unknown_session(self):
        result = await tool_meeting_status({"session_id": "nonexistent"})
        assert "not found" in result["content"][0]["text"]

    async def test_disconnect_unknown(self):
        result = await tool_meeting_disconnect({"session_id": "nonexistent"})
        assert "not found" in result["content"][0]["text"]

    async def test_connect_missing_url(self):
        result = await tool_meeting_connect({})
        assert "Provide join_url" in result["content"][0]["text"]

    async def test_connect_bad_url(self):
        result = await tool_meeting_connect({"join_url": "https://example.com/no-thread"})
        assert "Could not extract" in result["content"][0]["text"]


# ---------------------------------------------------------------------------
# Voice tools — state management (pure in-process, no external deps)
# ---------------------------------------------------------------------------

class TestVoiceTools:
    """Test voice state management."""

    @pytest.fixture(autouse=True)
    def _reset_voice(self):
        _voice_state.update({
            "enabled": False,
            "stt_backend": "whisper",
            "language": "en",
            "sample_rate": 16000,
            "chunk_duration_ms": 3000,
            "silence_threshold_ms": 800,
            "whisper_model": "base",
            "deepgram_api_key": "",
            "azure_speech_key": "",
            "azure_speech_region": "",
        })
        yield

    def test_voice_status_rpc(self):
        r = client.post("/rpc", json={
            "id": 1,
            "method": "tools/call",
            "params": {"name": "teams.voice.status", "arguments": {}},
        })
        assert r.status_code == 200
        text = r.json()["result"]["content"][0]["text"]
        assert "enabled: False" in text
        assert "stt_backend: whisper" in text

    def test_voice_toggle_rpc(self):
        r = client.post("/rpc", json={
            "id": 1,
            "method": "tools/call",
            "params": {"name": "teams.voice.toggle", "arguments": {"enabled": True}},
        })
        assert r.status_code == 200
        text = r.json()["result"]["content"][0]["text"]
        assert "enabled" in text
        assert get_voice_state()["enabled"] is True

    def test_voice_toggle_flip(self):
        assert get_voice_state()["enabled"] is False
        r = client.post("/rpc", json={
            "id": 1,
            "method": "tools/call",
            "params": {"name": "teams.voice.toggle", "arguments": {}},
        })
        assert r.status_code == 200
        assert get_voice_state()["enabled"] is True

    def test_voice_configure_rpc(self):
        r = client.post("/rpc", json={
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "teams.voice.configure",
                "arguments": {
                    "stt_backend": "deepgram",
                    "language": "es",
                    "whisper_model": "large-v3",
                    "chunk_duration_ms": 5000,
                },
            },
        })
        assert r.status_code == 200
        state = get_voice_state()
        assert state["stt_backend"] == "deepgram"
        assert state["language"] == "es"
        assert state["whisper_model"] == "large-v3"
        assert state["chunk_duration_ms"] == 5000

    def test_voice_configure_no_args(self):
        r = client.post("/rpc", json={
            "id": 1,
            "method": "tools/call",
            "params": {"name": "teams.voice.configure", "arguments": {}},
        })
        assert r.status_code == 200
        text = r.json()["result"]["content"][0]["text"]
        assert "No valid settings" in text

    def test_get_voice_state_returns_copy(self):
        state = get_voice_state()
        state["enabled"] = True
        assert _voice_state["enabled"] is False  # original unchanged


# ---------------------------------------------------------------------------
# OAuth scopes
# ---------------------------------------------------------------------------

class TestScopes:
    """Verify new scopes are present."""

    def test_new_scopes_included(self):
        from teams_mcp.auth.scopes import DEFAULT_SCOPES
        assert "ChatMessage.Read" in DEFAULT_SCOPES
        assert "ChatMember.Read" in DEFAULT_SCOPES
        assert "OnlineMeetings.Read" in DEFAULT_SCOPES

    def test_existing_scopes_preserved(self):
        from teams_mcp.auth.scopes import DEFAULT_SCOPES
        assert "offline_access" in DEFAULT_SCOPES
        assert "Chat.Read" in DEFAULT_SCOPES
        assert "Calendars.Read" in DEFAULT_SCOPES


# ---------------------------------------------------------------------------
# Tool schema validation
# ---------------------------------------------------------------------------

class TestToolSchemas:
    """Verify tool input schemas have required fields."""

    def _get_tool(self, name: str):
        for t in ALL_TOOLS:
            if t.name == name:
                return t
        pytest.fail(f"Tool {name} not found")

    def test_meeting_chat_resolve_schema(self):
        t = self._get_tool("teams.meeting_chat.resolve")
        assert "join_url" in t.input_schema["properties"]
        assert "join_url" in t.input_schema["required"]

    def test_meeting_chat_read_schema(self):
        t = self._get_tool("teams.meeting_chat.read")
        assert "chat_id" in t.input_schema["properties"]
        assert "top" in t.input_schema["properties"]

    def test_meeting_connect_schema(self):
        t = self._get_tool("teams.meeting.connect")
        assert "join_url" in t.input_schema["required"]
        assert "room_id" in t.input_schema["properties"]

    def test_voice_configure_schema(self):
        t = self._get_tool("teams.voice.configure")
        props = t.input_schema["properties"]
        assert "stt_backend" in props
        assert props["stt_backend"]["enum"] == ["whisper", "deepgram", "azure_speech"]
