from __future__ import annotations

from typing import Any, Dict

from ..rpc.types import Json, ToolDef, text_content

# Voice state — defaults to chat-only mode (STT disabled).
_voice_state: Dict[str, Any] = {
    "enabled": False,
    "stt_backend": "whisper",       # "whisper" | "deepgram" | "azure_speech"
    "language": "en",
    "sample_rate": 16000,
    "chunk_duration_ms": 3000,      # 3-second audio chunks
    "silence_threshold_ms": 800,    # silence gap to end utterance
    "whisper_model": "base",        # tiny | base | small | medium | large-v3
    "deepgram_api_key": "",
    "azure_speech_key": "",
    "azure_speech_region": "",
}


def get_voice_state() -> Dict[str, Any]:
    """Return a copy of the current voice state.

    Exported for use by the HomePilot TeamsBridge to query voice settings
    when deciding whether to start the STT pipeline.
    """
    return dict(_voice_state)


async def tool_voice_toggle(args: Json) -> Json:
    """Toggle STT on or off. Omit 'enabled' to flip the current state."""
    if "enabled" in args:
        _voice_state["enabled"] = bool(args["enabled"])
    else:
        _voice_state["enabled"] = not _voice_state["enabled"]

    status = "enabled" if _voice_state["enabled"] else "disabled"
    return text_content(f"Voice (STT) is now {status}.")


async def tool_voice_status(_: Json) -> Json:
    """Return current voice/STT configuration."""
    lines = ["Voice configuration:"]
    for k, v in _voice_state.items():
        display = v if not (isinstance(v, str) and "key" in k.lower() and v) else "***"
        lines.append(f"  {k}: {display}")
    return text_content("\n".join(lines))


async def tool_voice_configure(args: Json) -> Json:
    """Update voice/STT settings. Only provided fields are updated."""
    allowed_keys = {
        "stt_backend", "language", "whisper_model",
        "chunk_duration_ms", "silence_threshold_ms",
        "deepgram_api_key", "azure_speech_key", "azure_speech_region",
    }
    updated = []
    for key in allowed_keys:
        if key in args:
            val = args[key]
            if key in ("chunk_duration_ms", "silence_threshold_ms"):
                val = int(val)
            _voice_state[key] = val
            updated.append(key)

    if not updated:
        return text_content("No valid settings provided. Accepted: " + ", ".join(sorted(allowed_keys)))

    return text_content(f"Updated voice settings: {', '.join(sorted(updated))}")


async def tool_voice_transcribe(args: Json) -> Json:
    """Transcribe a base64-encoded audio chunk using the configured STT backend."""
    audio_b64 = args.get("audio_base64", "")
    if not audio_b64:
        return text_content("Error: 'audio_base64' is required.")

    if not _voice_state["enabled"]:
        return text_content("Error: Voice (STT) is disabled. Enable with teams.voice.toggle first.")

    try:
        from ..voice.stt_pipeline import transcribe
        segments = await transcribe(audio_b64, _voice_state)
    except ValueError as exc:
        return text_content(f"Error: {exc}")
    except RuntimeError as exc:
        return text_content(f"Error: {exc}")

    if not segments:
        return text_content("(silence — no speech detected)")

    lines = []
    for seg in segments:
        lines.append(f"[{seg['start']:.1f}s – {seg['end']:.1f}s] {seg['text']}")

    return text_content("\n".join(lines))


TOOLS = [
    ToolDef(
        name="teams.voice.toggle",
        description="Toggle speech-to-text on or off. Omit 'enabled' to flip. Default is OFF (chat-only mode).",
        input_schema={
            "type": "object",
            "properties": {
                "enabled": {"type": "boolean", "description": "True to enable, false to disable. Omit to toggle."},
            },
        },
        handler=tool_voice_toggle,
    ),
    ToolDef(
        name="teams.voice.status",
        description="Return current voice/STT configuration: enabled, backend, language, model, thresholds.",
        input_schema={"type": "object", "properties": {}},
        handler=tool_voice_status,
    ),
    ToolDef(
        name="teams.voice.configure",
        description="Update voice/STT settings. Only provided fields are changed.",
        input_schema={
            "type": "object",
            "properties": {
                "stt_backend": {"type": "string", "enum": ["whisper", "deepgram", "azure_speech"]},
                "language": {"type": "string", "description": "Language code (e.g. 'en', 'es')"},
                "whisper_model": {"type": "string", "enum": ["tiny", "base", "small", "medium", "large-v3"]},
                "chunk_duration_ms": {"type": "integer", "description": "Audio chunk duration in ms"},
                "silence_threshold_ms": {"type": "integer", "description": "Silence gap to end utterance in ms"},
                "deepgram_api_key": {"type": "string"},
                "azure_speech_key": {"type": "string"},
                "azure_speech_region": {"type": "string"},
            },
        },
        handler=tool_voice_configure,
    ),
    ToolDef(
        name="teams.voice.transcribe_chunk",
        description=(
            "Transcribe a base64-encoded audio chunk using the active STT backend. "
            "Voice must be enabled first (teams.voice.toggle). Audio should be raw PCM "
            "(mono, 16-bit LE, sample_rate from config) or WAV, base64-encoded."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "audio_base64": {
                    "type": "string",
                    "description": "Base64-encoded PCM or WAV audio bytes",
                },
            },
            "required": ["audio_base64"],
        },
        handler=tool_voice_transcribe,
    ),
]
