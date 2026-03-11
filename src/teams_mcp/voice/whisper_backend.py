"""Local Whisper STT backend using ``faster-whisper``.

The model is loaded lazily on first transcription and cached in-process.
Model size is controlled by ``voice_state["whisper_model"]``.

Requires: ``pip install faster-whisper>=1.0``
"""
from __future__ import annotations

import asyncio
import io
import logging
import wave
from typing import Any, Dict, List, Optional

from faster_whisper import WhisperModel  # type: ignore[import-untyped]

log = logging.getLogger("teams_mcp.voice.whisper")

_model: Optional[WhisperModel] = None
_model_size: Optional[str] = None


def _get_model(model_size: str) -> WhisperModel:
    """Return a cached WhisperModel, loading or replacing if size changed."""
    global _model, _model_size
    if _model is None or _model_size != model_size:
        log.info("Loading Whisper model: %s", model_size)
        _model = WhisperModel(model_size, device="cpu", compute_type="int8")
        _model_size = model_size
    return _model


def _pcm_to_wav(pcm: bytes, sample_rate: int, channels: int = 1, sample_width: int = 2) -> bytes:
    """Wrap raw PCM bytes in a WAV container."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()


def _run_whisper(pcm: bytes, state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Synchronous transcription — runs in thread pool."""
    model_size = state.get("whisper_model", "base")
    sample_rate = state.get("sample_rate", 16000)
    language = state.get("language", "en")

    model = _get_model(model_size)

    # faster-whisper accepts file-like objects (WAV)
    wav_bytes = _pcm_to_wav(pcm, sample_rate)
    audio_fp = io.BytesIO(wav_bytes)

    segments_iter, info = model.transcribe(
        audio_fp,
        language=language,
        beam_size=5,
        vad_filter=True,
    )

    results: List[Dict[str, Any]] = []
    for seg in segments_iter:
        results.append({
            "text": seg.text.strip(),
            "start": round(seg.start, 3),
            "end": round(seg.end, 3),
            "language": info.language,
        })

    log.info("Whisper transcribed %d segments (lang=%s)", len(results), info.language)
    return results


async def transcribe_whisper(pcm: bytes, state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Async wrapper — offloads the blocking Whisper call to a thread."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _run_whisper, pcm, state)
