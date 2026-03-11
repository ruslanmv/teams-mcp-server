"""
Unit tests for the voice/STT pipeline and ACS tools.

These tests verify:
- STT pipeline routing logic (without real audio backends)
- Voice transcribe_chunk tool (disabled state, missing args, bad input)
- ACS session lifecycle (join, status, leave — no Azure SDK needed)
- ACS tool schema validation
- Tool registration counts (35 total after P2+P3+persona)
"""
import base64

import pytest
from fastapi.testclient import TestClient

from teams_mcp.main import app
from teams_mcp.tools import ALL_TOOLS
from teams_mcp.tools.tools_voice import (
    _voice_state,
    get_voice_state,
    tool_voice_transcribe,
)
from teams_mcp.acs.client import _acs_sessions, acs_join, acs_leave, acs_status


client = TestClient(app)


# ---------------------------------------------------------------------------
# Tool counts (updated for P2 + P3)
# ---------------------------------------------------------------------------

class TestToolCountsP2P3:
    """Verify total tool count after adding transcribe_chunk + 3 ACS + 8 persona tools."""

    def test_total_tools_35(self):
        # 23 (previous) + 1 (transcribe_chunk) + 3 (ACS) + 8 (persona) = 35
        assert len(ALL_TOOLS) == 35, f"Expected 35 tools, got {len(ALL_TOOLS)}"

    def test_new_p2_tools_registered(self):
        names = {t.name for t in ALL_TOOLS}
        assert "teams.voice.transcribe_chunk" in names

    def test_new_p3_tools_registered(self):
        names = {t.name for t in ALL_TOOLS}
        assert "teams.acs.join" in names
        assert "teams.acs.status" in names
        assert "teams.acs.leave" in names

    def test_health_shows_35_tools(self):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert len(data["tools"]) == 35

    def test_rpc_tools_list_includes_new(self):
        r = client.post("/rpc", json={"id": 1, "method": "tools/list", "params": {}})
        names = {t["name"] for t in r.json()["result"]}
        assert "teams.voice.transcribe_chunk" in names
        assert "teams.acs.join" in names


# ---------------------------------------------------------------------------
# Voice transcribe_chunk tool
# ---------------------------------------------------------------------------

class TestVoiceTranscribe:
    """Test the transcribe_chunk tool without real STT backends."""

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

    async def test_transcribe_disabled(self):
        result = await tool_voice_transcribe({"audio_base64": "AAAA"})
        text = result["content"][0]["text"]
        assert "disabled" in text

    async def test_transcribe_missing_audio(self):
        _voice_state["enabled"] = True
        result = await tool_voice_transcribe({})
        text = result["content"][0]["text"]
        assert "audio_base64" in text

    async def test_transcribe_empty_audio(self):
        _voice_state["enabled"] = True
        result = await tool_voice_transcribe({"audio_base64": ""})
        text = result["content"][0]["text"]
        assert "audio_base64" in text

    async def test_transcribe_invalid_base64(self):
        _voice_state["enabled"] = True
        result = await tool_voice_transcribe({"audio_base64": "!!!not-base64!!!"})
        text = result["content"][0]["text"]
        assert "Error" in text

    async def test_transcribe_whisper_not_installed(self):
        """When faster-whisper is not installed, should get a clear error."""
        _voice_state["enabled"] = True
        # Valid base64 but actual transcription will fail because
        # faster-whisper is not installed in the test env
        audio = base64.b64encode(b"\x00" * 3200).decode()
        result = await tool_voice_transcribe({"audio_base64": audio})
        text = result["content"][0]["text"]
        # Should either fail with import error or transcription error
        assert "Error" in text or "silence" in text

    async def test_transcribe_deepgram_no_key(self):
        _voice_state["enabled"] = True
        _voice_state["stt_backend"] = "deepgram"
        audio = base64.b64encode(b"\x00" * 3200).decode()
        result = await tool_voice_transcribe({"audio_base64": audio})
        text = result["content"][0]["text"]
        assert "Error" in text
        assert "key" in text.lower() or "deepgram" in text.lower()

    async def test_transcribe_azure_no_key(self):
        _voice_state["enabled"] = True
        _voice_state["stt_backend"] = "azure_speech"
        audio = base64.b64encode(b"\x00" * 3200).decode()
        result = await tool_voice_transcribe({"audio_base64": audio})
        text = result["content"][0]["text"]
        assert "Error" in text

    def test_transcribe_chunk_rpc_disabled(self):
        r = client.post("/rpc", json={
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "teams.voice.transcribe_chunk",
                "arguments": {"audio_base64": "AAAA"},
            },
        })
        assert r.status_code == 200
        text = r.json()["result"]["content"][0]["text"]
        assert "disabled" in text

    def test_transcribe_chunk_schema(self):
        t = next(t for t in ALL_TOOLS if t.name == "teams.voice.transcribe_chunk")
        assert "audio_base64" in t.input_schema["properties"]
        assert "audio_base64" in t.input_schema["required"]


# ---------------------------------------------------------------------------
# STT pipeline routing (unit-level)
# ---------------------------------------------------------------------------

class TestSttPipelineRouting:
    """Test the pipeline module's routing logic."""

    async def test_empty_audio_raises(self):
        from teams_mcp.voice.stt_pipeline import transcribe
        with pytest.raises(ValueError, match="empty"):
            await transcribe("", {"stt_backend": "whisper"})

    async def test_invalid_base64_raises(self):
        from teams_mcp.voice.stt_pipeline import transcribe
        with pytest.raises(ValueError, match="Invalid base64"):
            await transcribe("!!!invalid!!!", {"stt_backend": "whisper"})

    async def test_zero_bytes_raises(self):
        from teams_mcp.voice.stt_pipeline import transcribe
        # base64 of empty bytes produces empty string → caught as "empty"
        with pytest.raises(ValueError, match="empty"):
            await transcribe(base64.b64encode(b"").decode(), {"stt_backend": "whisper"})

    async def test_unknown_backend_raises(self):
        from teams_mcp.voice.stt_pipeline import transcribe
        audio = base64.b64encode(b"\x00" * 100).decode()
        with pytest.raises(RuntimeError, match="Unknown STT backend"):
            await transcribe(audio, {"stt_backend": "nonexistent"})


# ---------------------------------------------------------------------------
# ACS session lifecycle
# ---------------------------------------------------------------------------

class TestAcsSessions:
    """Test ACS join/status/leave without Azure SDK."""

    @pytest.fixture(autouse=True)
    def _clear_sessions(self):
        _acs_sessions.clear()
        yield
        _acs_sessions.clear()

    async def test_status_no_sessions(self):
        sessions = await acs_status()
        assert sessions == []

    async def test_status_unknown_session(self):
        sessions = await acs_status("nonexistent")
        assert sessions == []

    async def test_join_valid_connection_string(self):
        session = await acs_join(
            join_url="https://teams.microsoft.com/l/meetup-join/test/0",
            connection_string="endpoint=https://test.communication.azure.com/;accesskey=abc123",
        )
        assert session.session_id.startswith("acs-")
        assert session.status == "pending_sdk"
        assert session.error is None

    async def test_join_invalid_connection_string(self):
        session = await acs_join(
            join_url="https://teams.microsoft.com/l/meetup-join/test/0",
            connection_string="bad-format",
        )
        assert session.status == "error"
        assert "Invalid ACS connection string" in session.error

    async def test_leave_existing(self):
        session = await acs_join(
            join_url="https://teams.microsoft.com/test",
            connection_string="endpoint=https://test.communication.azure.com/;accesskey=abc",
        )
        result = await acs_leave(session.session_id)
        assert result is not None
        assert result.status == "disconnected"

    async def test_leave_nonexistent(self):
        result = await acs_leave("nonexistent")
        assert result is None

    async def test_status_after_join(self):
        await acs_join(
            join_url="https://teams.microsoft.com/test",
            connection_string="endpoint=https://test.communication.azure.com/;accesskey=abc",
        )
        sessions = await acs_status()
        assert len(sessions) == 1
        assert sessions[0]["status"] == "pending_sdk"

    async def test_multiple_sessions(self):
        await acs_join(
            join_url="https://teams.microsoft.com/test1",
            connection_string="endpoint=https://test.communication.azure.com/;accesskey=abc",
        )
        await acs_join(
            join_url="https://teams.microsoft.com/test2",
            connection_string="endpoint=https://test.communication.azure.com/;accesskey=xyz",
        )
        sessions = await acs_status()
        assert len(sessions) == 2


# ---------------------------------------------------------------------------
# ACS tools via RPC
# ---------------------------------------------------------------------------

class TestAcsToolsRpc:
    """Test ACS tools via the RPC endpoint."""

    @pytest.fixture(autouse=True)
    def _clear_sessions(self):
        _acs_sessions.clear()
        yield
        _acs_sessions.clear()

    def test_acs_join_missing_url(self):
        r = client.post("/rpc", json={
            "id": 1,
            "method": "tools/call",
            "params": {"name": "teams.acs.join", "arguments": {"connection_string": "x"}},
        })
        assert r.status_code == 200
        text = r.json()["result"]["content"][0]["text"]
        assert "join_url" in text

    def test_acs_join_missing_conn(self):
        r = client.post("/rpc", json={
            "id": 1,
            "method": "tools/call",
            "params": {"name": "teams.acs.join", "arguments": {"join_url": "x"}},
        })
        assert r.status_code == 200
        text = r.json()["result"]["content"][0]["text"]
        assert "connection_string" in text

    def test_acs_status_empty(self):
        r = client.post("/rpc", json={
            "id": 1,
            "method": "tools/call",
            "params": {"name": "teams.acs.status", "arguments": {}},
        })
        assert r.status_code == 200
        text = r.json()["result"]["content"][0]["text"]
        assert "No ACS sessions" in text

    def test_acs_leave_missing_id(self):
        r = client.post("/rpc", json={
            "id": 1,
            "method": "tools/call",
            "params": {"name": "teams.acs.leave", "arguments": {}},
        })
        assert r.status_code == 200
        text = r.json()["result"]["content"][0]["text"]
        assert "session_id" in text

    def test_acs_join_schema(self):
        t = next(t for t in ALL_TOOLS if t.name == "teams.acs.join")
        assert "join_url" in t.input_schema["required"]
        assert "connection_string" in t.input_schema["required"]

    def test_acs_leave_schema(self):
        t = next(t for t in ALL_TOOLS if t.name == "teams.acs.leave")
        assert "session_id" in t.input_schema["required"]
