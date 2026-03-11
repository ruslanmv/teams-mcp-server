"""Static face video generation and audio injection for persona meetings.

Generates an MJPEG file from a static face PNG with idle animation
(subtle sway + periodic blink) that Chromium uses as fake video capture.

Also provides helpers for routing TTS audio to the browser via a virtual
audio device (PulseAudio/PipeWire).
"""
from __future__ import annotations

import asyncio
import logging
import math
import struct
import tempfile
from pathlib import Path
from typing import Optional

log = logging.getLogger("teams_mcp.browser.media_inject")

# ---------------------------------------------------------------------------
# Face video generation (static PNG → animated Y4M)
# ---------------------------------------------------------------------------

def generate_face_video(
    face_image_path: str,
    output_path: Optional[str] = None,
    fps: int = 15,
    duration_s: int = 3600,
    sway_px: int = 2,
    blink_interval_frames: int = 75,
) -> str:
    """Generate a looping Y4M video file from a static face image.

    The video includes subtle idle animation:
      - Gentle sway (±sway_px pixels, sine wave)
      - Periodic blink (darken eye region every blink_interval_frames)

    Parameters
    ----------
    face_image_path : str
        Path to the persona's face image (PNG/JPG).
    output_path : str, optional
        Where to write the Y4M file. Auto-generates temp file if None.
    fps : int
        Frames per second (default 15).
    duration_s : int
        Video duration in seconds (default 3600 = 1 hour loop).
    sway_px : int
        Max pixel displacement for idle sway.
    blink_interval_frames : int
        Blink every N frames.

    Returns
    -------
    str
        Path to the generated video file.
    """
    try:
        import cv2
        import numpy as np
    except ImportError:
        raise RuntimeError(
            "Face video generation requires 'opencv-python-headless'. "
            "Install with: pip install 'teams-mcp-server[persona]'"
        )

    face = cv2.imread(face_image_path)
    if face is None:
        raise FileNotFoundError(f"Cannot read face image: {face_image_path}")

    # Resize to 640x480 for webcam compatibility
    face = cv2.resize(face, (640, 480))
    h, w = face.shape[:2]

    if output_path is None:
        output_path = tempfile.mktemp(suffix=".y4m", prefix="persona_face_")

    total_frames = fps * duration_s
    log.info(
        "Generating face video: %s → %s (%d fps, %d frames)",
        face_image_path, output_path, fps, total_frames,
    )

    # We write a short looping segment (10s) — Chrome loops Y4M automatically
    loop_frames = fps * 10  # 10 seconds of unique frames

    with open(output_path, "wb") as f:
        # Y4M header
        f.write(f"YUV4MPEG2 W{w} H{h} F{fps}:1 Ip A1:1 C420jpeg\n".encode())

        for i in range(loop_frames):
            frame = face.copy()

            # Subtle sway
            dx = int(sway_px * math.sin(i * 0.3))
            dy = int(max(1, sway_px // 2) * math.sin(i * 0.2))
            M = np.float32([[1, 0, dx], [0, 1, dy]])
            frame = cv2.warpAffine(frame, M, (w, h), borderMode=cv2.BORDER_REFLECT)

            # Periodic blink (darken upper third, center strip)
            if i % blink_interval_frames == 0:
                eye_y1 = int(h * 0.28)
                eye_y2 = int(h * 0.38)
                eye_x1 = int(w * 0.25)
                eye_x2 = int(w * 0.75)
                frame[eye_y1:eye_y2, eye_x1:eye_x2] = (
                    frame[eye_y1:eye_y2, eye_x1:eye_x2] * 0.3
                ).astype(np.uint8)

            # Convert BGR → YUV420p (Y4M format)
            yuv = cv2.cvtColor(frame, cv2.COLOR_BGR2YUV_I420)
            f.write(b"FRAME\n")
            f.write(yuv.tobytes())

    log.info("Face video generated: %s (%.1f MB)", output_path, Path(output_path).stat().st_size / 1e6)
    return output_path


# ---------------------------------------------------------------------------
# Audio injection: TTS → virtual audio device → browser mic
# ---------------------------------------------------------------------------

async def setup_virtual_audio() -> dict:
    """Create a PulseAudio/PipeWire virtual sink for TTS output.

    The browser picks this up as its "microphone" input.

    Returns
    -------
    dict with sink_name and monitor_source.
    """
    sink_name = "persona_tts_sink"

    # Check if already exists
    check = await asyncio.create_subprocess_shell(
        f"pactl list sinks short | grep {sink_name}",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await check.communicate()
    if sink_name.encode() in stdout:
        log.info("Virtual audio sink already exists: %s", sink_name)
        return {"sink_name": sink_name, "monitor_source": f"{sink_name}.monitor"}

    # Create virtual sink
    proc = await asyncio.create_subprocess_shell(
        f'pactl load-module module-null-sink sink_name={sink_name} '
        f'sink_properties=device.description="Persona_TTS"',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        log.warning("Could not create virtual audio sink: %s", stderr.decode())
        return {"sink_name": None, "monitor_source": None, "error": stderr.decode()}

    log.info("Created virtual audio sink: %s", sink_name)
    return {"sink_name": sink_name, "monitor_source": f"{sink_name}.monitor"}


async def play_audio_to_sink(audio_path: str, sink_name: str = "persona_tts_sink") -> bool:
    """Play a WAV/PCM file to the virtual audio sink.

    Parameters
    ----------
    audio_path : str
        Path to WAV file.
    sink_name : str
        PulseAudio sink name.

    Returns
    -------
    bool : True if playback succeeded.
    """
    proc = await asyncio.create_subprocess_exec(
        "paplay", "--device", sink_name, audio_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        log.warning("Audio playback failed: %s", stderr.decode())
        return False

    log.info("Played audio to sink %s: %s", sink_name, audio_path)
    return True


async def cleanup_virtual_audio(sink_name: str = "persona_tts_sink") -> None:
    """Remove the virtual audio sink."""
    proc = await asyncio.create_subprocess_shell(
        f"pactl list modules short | grep {sink_name}",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    if stdout:
        module_id = stdout.decode().split()[0]
        await asyncio.create_subprocess_exec(
            "pactl", "unload-module", module_id,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        log.info("Removed virtual audio sink: %s", sink_name)


# ---------------------------------------------------------------------------
# TTS generation (piper-tts)
# ---------------------------------------------------------------------------

async def text_to_speech(
    text: str,
    voice_model: str = "en_US-amy-medium",
    output_path: Optional[str] = None,
) -> str:
    """Generate speech audio from text using piper-tts.

    Parameters
    ----------
    text : str
        Text to speak.
    voice_model : str
        Piper voice model name.
    output_path : str, optional
        WAV output path. Auto-generates temp file if None.

    Returns
    -------
    str : Path to the generated WAV file.
    """
    if output_path is None:
        output_path = tempfile.mktemp(suffix=".wav", prefix="persona_tts_")

    # Try piper CLI first (most common installation)
    proc = await asyncio.create_subprocess_exec(
        "piper",
        "--model", voice_model,
        "--output_file", output_path,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate(input=text.encode("utf-8"))

    if proc.returncode != 0:
        # Fallback: try piper-tts Python package
        try:
            from piper import PiperVoice
            voice = PiperVoice.load(voice_model)
            import wave
            with wave.open(output_path, "wb") as wav:
                voice.synthesize(text, wav)
            log.info("TTS via piper Python: %s", output_path)
            return output_path
        except ImportError:
            raise RuntimeError(
                f"piper-tts not found. Install with: pip install piper-tts "
                f"or install the piper CLI. Error: {stderr.decode()}"
            )

    log.info("TTS generated: %s (%d chars → %s)", voice_model, len(text), output_path)
    return output_path


# ---------------------------------------------------------------------------
# Audio capture from browser tab
# ---------------------------------------------------------------------------

async def capture_tab_audio_chunk(page, duration_ms: int = 3000) -> Optional[bytes]:
    """Capture audio from the browser tab using Web Audio API.

    Injects a script that records from the tab's audio context
    and returns base64-encoded PCM data.

    Parameters
    ----------
    page : Playwright Page
        The active meeting page.
    duration_ms : int
        Duration to capture in milliseconds.

    Returns
    -------
    bytes or None : Raw PCM audio bytes, or None if capture failed.
    """
    import base64

    try:
        audio_b64 = await page.evaluate(f"""async () => {{
            try {{
                // Get audio from the page's media streams
                const streams = document.querySelectorAll('audio, video');
                let stream = null;

                for (const el of streams) {{
                    if (el.srcObject) {{
                        stream = el.srcObject;
                        break;
                    }}
                }}

                if (!stream) {{
                    // Try to capture tab audio via AudioContext
                    const ctx = new AudioContext({{sampleRate: 16000}});
                    const dest = ctx.createMediaStreamDestination();
                    stream = dest.stream;
                }}

                if (!stream || stream.getAudioTracks().length === 0) {{
                    return null;
                }}

                const recorder = new MediaRecorder(stream, {{mimeType: 'audio/webm'}});
                const chunks = [];

                return new Promise((resolve) => {{
                    recorder.ondataavailable = (e) => chunks.push(e.data);
                    recorder.onstop = async () => {{
                        const blob = new Blob(chunks, {{type: 'audio/webm'}});
                        const buffer = await blob.arrayBuffer();
                        const base64 = btoa(
                            new Uint8Array(buffer).reduce(
                                (data, byte) => data + String.fromCharCode(byte), ''
                            )
                        );
                        resolve(base64);
                    }};
                    recorder.start();
                    setTimeout(() => recorder.stop(), {duration_ms});
                }});
            }} catch (e) {{
                return null;
            }}
        }}""")

        if audio_b64:
            return base64.b64decode(audio_b64)
        return None

    except Exception as e:
        log.warning("Tab audio capture failed: %s", e)
        return None
