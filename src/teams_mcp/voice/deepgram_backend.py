"""Cloud Deepgram STT backend via WebSocket.

Sends a single audio chunk to the Deepgram streaming API and collects
the final transcript.  For short chunks (≤10s) this is a simple
open → send → close → collect pattern rather than a long-lived stream.

Requires: ``pip install websockets>=12.0``
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

import websockets  # type: ignore[import-untyped]

log = logging.getLogger("teams_mcp.voice.deepgram")

_DG_WS_URL = "wss://api.deepgram.com/v1/listen"


async def transcribe_deepgram(pcm: bytes, state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Send PCM audio to Deepgram and return transcription segments.

    Parameters
    ----------
    pcm:
        Raw PCM bytes (mono, 16-bit signed LE).
    state:
        Voice configuration dict.  Must contain ``deepgram_api_key``.
    """
    api_key = state.get("deepgram_api_key", "")
    if not api_key:
        raise RuntimeError(
            "Deepgram API key not configured.  "
            "Set it via teams.voice.configure(deepgram_api_key='...')"
        )

    sample_rate = state.get("sample_rate", 16000)
    language = state.get("language", "en")

    url = (
        f"{_DG_WS_URL}"
        f"?encoding=linear16"
        f"&sample_rate={sample_rate}"
        f"&channels=1"
        f"&language={language}"
        f"&punctuate=true"
        f"&utterances=true"
        f"&model=nova-2"
    )

    headers = {"Authorization": f"Token {api_key}"}

    results: List[Dict[str, Any]] = []

    async with websockets.connect(url, additional_headers=headers) as ws:
        # Send audio in one shot (chunk-level, not streaming)
        await ws.send(pcm)

        # Signal end of audio
        await ws.send(json.dumps({"type": "CloseStream"}))

        # Collect results until connection closes
        async for raw_msg in ws:
            msg = json.loads(raw_msg)
            msg_type = msg.get("type", "")

            if msg_type == "Results" and msg.get("is_final"):
                channel = msg.get("channel", {})
                alternatives = channel.get("alternatives", [])
                if alternatives:
                    alt = alternatives[0]
                    text = alt.get("transcript", "").strip()
                    if text:
                        start = msg.get("start", 0.0)
                        duration = msg.get("duration", 0.0)
                        results.append({
                            "text": text,
                            "start": round(start, 3),
                            "end": round(start + duration, 3),
                            "language": language,
                        })

            elif msg_type == "UtteranceEnd":
                # Deepgram signals utterance boundaries
                pass

    log.info("Deepgram transcribed %d segments", len(results))
    return results
