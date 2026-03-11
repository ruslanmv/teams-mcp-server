"""Azure Cognitive Services Speech-to-Text backend.

Uses the ``azure-cognitiveservices-speech`` SDK to transcribe a single
audio chunk.  The SDK is heavy (~200 MB) so it is only imported when
this backend is actually selected.

Requires: ``pip install azure-cognitiveservices-speech>=1.37``
"""
from __future__ import annotations

import asyncio
import io
import logging
import wave
from typing import Any, Dict, List

import azure.cognitiveservices.speech as speechsdk  # type: ignore[import-untyped]

log = logging.getLogger("teams_mcp.voice.azure_speech")


def _pcm_to_wav(pcm: bytes, sample_rate: int, channels: int = 1, sample_width: int = 2) -> bytes:
    """Wrap raw PCM bytes in a WAV container for the Azure SDK."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()


def _run_azure(pcm: bytes, state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Synchronous Azure Speech recognition — runs in thread pool."""
    speech_key = state.get("azure_speech_key", "")
    speech_region = state.get("azure_speech_region", "")
    if not speech_key or not speech_region:
        raise RuntimeError(
            "Azure Speech key/region not configured.  "
            "Set via teams.voice.configure(azure_speech_key='...', azure_speech_region='...')"
        )

    sample_rate = state.get("sample_rate", 16000)
    language = state.get("language", "en")

    # Map short language codes to Azure locale codes
    lang_map: Dict[str, str] = {
        "en": "en-US", "es": "es-ES", "fr": "fr-FR", "de": "de-DE",
        "it": "it-IT", "pt": "pt-BR", "ja": "ja-JP", "zh": "zh-CN",
        "ko": "ko-KR", "ru": "ru-RU", "ar": "ar-SA", "hi": "hi-IN",
    }
    locale = lang_map.get(language, language)

    speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=speech_region)
    speech_config.speech_recognition_language = locale

    # Create an audio stream from the PCM data
    wav_bytes = _pcm_to_wav(pcm, sample_rate)
    audio_stream = speechsdk.audio.PushAudioInputStream(
        stream_format=speechsdk.audio.AudioStreamFormat(
            samples_per_second=sample_rate,
            bits_per_sample=16,
            channels=1,
        )
    )
    audio_stream.write(wav_bytes)
    audio_stream.close()

    audio_config = speechsdk.audio.AudioConfig(stream=audio_stream)
    recognizer = speechsdk.SpeechRecognizer(
        speech_config=speech_config,
        audio_config=audio_config,
    )

    # Single-shot recognition for chunk-level audio
    result = recognizer.recognize_once()

    results: List[Dict[str, Any]] = []

    if result.reason == speechsdk.ResultReason.RecognizedSpeech:
        # Duration is in ticks (100 nanosecond units)
        duration_sec = result.duration / 10_000_000 if result.duration else 0.0
        offset_sec = result.offset / 10_000_000 if result.offset else 0.0
        results.append({
            "text": result.text.strip(),
            "start": round(offset_sec, 3),
            "end": round(offset_sec + duration_sec, 3),
            "language": locale,
        })
    elif result.reason == speechsdk.ResultReason.NoMatch:
        log.info("Azure Speech: no match (silence or noise)")
    elif result.reason == speechsdk.ResultReason.Canceled:
        cancellation = result.cancellation_details
        log.warning("Azure Speech canceled: %s — %s", cancellation.reason, cancellation.error_details)

    log.info("Azure Speech transcribed %d segments", len(results))
    return results


async def transcribe_azure(pcm: bytes, state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Async wrapper — offloads the blocking Azure SDK call to a thread."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _run_azure, pcm, state)
