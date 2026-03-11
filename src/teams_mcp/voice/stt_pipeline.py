"""Unified STT pipeline — routes audio to the configured backend.

Usage::

    from teams_mcp.voice.stt_pipeline import transcribe
    segments = await transcribe(pcm_bytes, state)
    # → [{"text": "hello world", "start": 0.0, "end": 2.3, "language": "en"}]

All heavy imports (faster-whisper, websockets, azure.cognitiveservices.speech)
are deferred to the backend modules so the server starts fast even when the
optional dependencies are not installed.
"""
from __future__ import annotations

import base64
import logging
from typing import Any, Dict, List

log = logging.getLogger("teams_mcp.voice.pipeline")

# Type alias for a transcription segment
Segment = Dict[str, Any]


async def transcribe(audio_b64: str, voice_state: Dict[str, Any]) -> List[Segment]:
    """Decode base64 audio and route to the active STT backend.

    Parameters
    ----------
    audio_b64:
        Base64-encoded raw PCM (mono, ``voice_state["sample_rate"]`` Hz,
        16-bit signed little-endian) or WAV bytes.
    voice_state:
        Current voice configuration dict (from ``get_voice_state()``).

    Returns
    -------
    list[Segment]
        Each segment is ``{"text": str, "start": float, "end": float, "language": str}``.

    Raises
    ------
    RuntimeError
        If the selected backend's optional dependency is not installed.
    ValueError
        If audio_b64 is empty or cannot be decoded.
    """
    if not audio_b64:
        raise ValueError("audio_b64 is empty")

    try:
        pcm_bytes = base64.b64decode(audio_b64)
    except Exception as exc:
        raise ValueError(f"Invalid base64 audio: {exc}") from exc

    if len(pcm_bytes) == 0:
        raise ValueError("Decoded audio is 0 bytes")

    backend = voice_state.get("stt_backend", "whisper")
    language = voice_state.get("language", "en")

    log.info("transcribe: backend=%s  bytes=%d  lang=%s", backend, len(pcm_bytes), language)

    if backend == "whisper":
        return await _transcribe_whisper(pcm_bytes, voice_state)
    elif backend == "deepgram":
        return await _transcribe_deepgram(pcm_bytes, voice_state)
    elif backend == "azure_speech":
        return await _transcribe_azure(pcm_bytes, voice_state)
    else:
        raise RuntimeError(f"Unknown STT backend: {backend!r}")


# ---------------------------------------------------------------------------
# Backend dispatchers — thin wrappers that import lazily
# ---------------------------------------------------------------------------

async def _transcribe_whisper(pcm: bytes, state: Dict[str, Any]) -> List[Segment]:
    try:
        from .whisper_backend import transcribe_whisper
    except ImportError as exc:
        raise RuntimeError(
            "Whisper backend requires 'faster-whisper'.  "
            "Install with:  pip install 'teams-mcp-server[whisper]'"
        ) from exc
    return await transcribe_whisper(pcm, state)


async def _transcribe_deepgram(pcm: bytes, state: Dict[str, Any]) -> List[Segment]:
    try:
        from .deepgram_backend import transcribe_deepgram
    except ImportError as exc:
        raise RuntimeError(
            "Deepgram backend requires 'websockets'.  "
            "Install with:  pip install 'teams-mcp-server[deepgram]'"
        ) from exc
    return await transcribe_deepgram(pcm, state)


async def _transcribe_azure(pcm: bytes, state: Dict[str, Any]) -> List[Segment]:
    try:
        from .azure_speech_backend import transcribe_azure
    except ImportError as exc:
        raise RuntimeError(
            "Azure Speech backend requires 'azure-cognitiveservices-speech'.  "
            "Install with:  pip install 'teams-mcp-server[azure_speech]'"
        ) from exc
    return await transcribe_azure(pcm, state)
