"""Persona meeting tools — browser-based guest join with static face + TTS/STT.

These tools allow a persona (AI agent) to join a Teams meeting as a named
guest using a headless browser. No Azure registration is required.

Tools:
  - teams.persona.join       — Launch browser, join meeting as guest
  - teams.persona.leave      — Leave meeting and close browser
  - teams.persona.status     — Session health check
  - teams.persona.set_face   — Load static face image for virtual camera
  - teams.persona.speak      — TTS text → route audio to meeting
  - teams.persona.listen     — Capture meeting audio → STT → transcript
  - teams.persona.chat_post  — Post message in meeting chat via DOM
  - teams.persona.chat_read  — Read meeting chat messages via DOM
"""
from __future__ import annotations

import base64
import logging
import time
from typing import Any, Dict

from ..rpc.types import Json, ToolDef, text_content, error_content

log = logging.getLogger("teams_mcp.tools.persona")

# In-process persona session registry
_persona_sessions: Dict[str, Dict[str, Any]] = {}


def _new_session_id() -> str:
    return f"persona-{int(time.time() * 1000)}"


def _get_session(args: Json) -> tuple[str, Dict[str, Any] | None]:
    sid = str(args.get("session_id", "")).strip()
    if not sid:
        return "", None
    return sid, _persona_sessions.get(sid)


# -----------------------------------------------------------------------
# teams.persona.join
# -----------------------------------------------------------------------

async def tool_persona_join(args: Json) -> Json:
    """Launch headless browser and join a Teams meeting as a named guest."""
    join_url = str(args.get("join_url", "")).strip()
    display_name = str(args.get("display_name", "")).strip()

    if not join_url:
        return error_content("'join_url' is required.")
    if not display_name:
        return error_content("'display_name' is required.")

    face_image = str(args.get("face_image", "")).strip() or None
    headless = args.get("headless", True)

    try:
        from ..browser.guest_join import PersonaBrowser
    except ImportError as exc:
        return error_content(
            "Persona mode requires 'playwright'. "
            "Install with: pip install 'teams-mcp-server[persona]' && playwright install chromium"
        )

    session_id = _new_session_id()

    # Generate face video if image provided
    face_video_path = None
    if face_image:
        try:
            from ..browser.media_inject import generate_face_video
            face_video_path = generate_face_video(face_image)
        except Exception as e:
            log.warning("Face video generation failed (continuing without): %s", e)

    # Launch browser
    browser = PersonaBrowser(session_id)
    try:
        result = await browser.launch(
            join_url=join_url,
            display_name=display_name,
            face_video_path=face_video_path,
            headless=headless,
        )
    except Exception as e:
        await browser.close()
        return error_content(f"Failed to join meeting: {e}")

    # Store session
    _persona_sessions[session_id] = {
        "session_id": session_id,
        "browser": browser,
        "join_url": join_url,
        "display_name": display_name,
        "face_image": face_image,
        "face_video_path": face_video_path,
        "status": "joined" if browser.joined else "joining",
        "connected_at": time.time(),
        "audio_active": False,
        "video_active": face_video_path is not None,
        "tts_voice": args.get("tts_voice", "en_US-amy-medium"),
    }

    return text_content(
        f"Persona joined meeting.\n"
        f"  session_id: {session_id}\n"
        f"  display_name: {display_name}\n"
        f"  status: {result.get('status', 'unknown')}\n"
        f"  video: {'face loaded' if face_video_path else 'no face (camera off)'}\n"
        f"  join_url: {join_url[:80]}..."
    )


# -----------------------------------------------------------------------
# teams.persona.leave
# -----------------------------------------------------------------------

async def tool_persona_leave(args: Json) -> Json:
    """Leave the Teams meeting and close the browser."""
    sid, session = _get_session(args)
    if not sid:
        return error_content("'session_id' is required.")
    if not session:
        return error_content(f"Session {sid} not found.")

    browser = session.get("browser")
    if browser:
        await browser.leave()

    # Cleanup virtual audio if it was set up
    try:
        from ..browser.media_inject import cleanup_virtual_audio
        await cleanup_virtual_audio()
    except Exception:
        pass

    _persona_sessions.pop(sid, None)
    return text_content(f"Persona session {sid} disconnected. Browser closed.")


# -----------------------------------------------------------------------
# teams.persona.status
# -----------------------------------------------------------------------

async def tool_persona_status(args: Json) -> Json:
    """Return persona session info. Omit session_id to list all."""
    sid = str(args.get("session_id", "")).strip()

    if sid:
        session = _persona_sessions.get(sid)
        if not session:
            return text_content(f"Session {sid} not found.")

        browser = session.get("browser")
        lines = [
            f"Persona Session: {sid}",
            f"  display_name: {session['display_name']}",
            f"  status: {session['status']}",
            f"  joined: {browser.joined if browser else False}",
            f"  video_active: {session['video_active']}",
            f"  audio_active: {session['audio_active']}",
            f"  tts_voice: {session['tts_voice']}",
            f"  connected_at: {session['connected_at']}",
            f"  uptime_s: {int(time.time() - session['connected_at'])}",
        ]
        return text_content("\n".join(lines))

    if not _persona_sessions:
        return text_content("No active persona sessions.")

    lines = [f"Active persona sessions ({len(_persona_sessions)}):"]
    for s_id, s in _persona_sessions.items():
        lines.append(
            f"- {s_id} | {s['display_name']} | {s['status']} | "
            f"video={s['video_active']} audio={s['audio_active']}"
        )
    return text_content("\n".join(lines))


# -----------------------------------------------------------------------
# teams.persona.set_face
# -----------------------------------------------------------------------

async def tool_persona_set_face(args: Json) -> Json:
    """Load a static face image for the persona's virtual camera."""
    sid, session = _get_session(args)
    if not sid:
        return error_content("'session_id' is required.")
    if not session:
        return error_content(f"Session {sid} not found.")

    image_path = str(args.get("image_path", "")).strip()
    if not image_path:
        return error_content("'image_path' is required.")

    try:
        from ..browser.media_inject import generate_face_video
        video_path = generate_face_video(image_path)
    except Exception as e:
        return error_content(f"Failed to generate face video: {e}")

    session["face_image"] = image_path
    session["face_video_path"] = video_path
    session["video_active"] = True

    return text_content(
        f"Face loaded for session {sid}.\n"
        f"  image: {image_path}\n"
        f"  video: {video_path}\n"
        f"  Note: Face video is used on next browser launch. "
        f"For a running session, the face was set at join time."
    )


# -----------------------------------------------------------------------
# teams.persona.speak
# -----------------------------------------------------------------------

async def tool_persona_speak(args: Json) -> Json:
    """Generate TTS audio from text and play it into the meeting."""
    sid, session = _get_session(args)
    if not sid:
        return error_content("'session_id' is required.")
    if not session:
        return error_content(f"Session {sid} not found.")

    text = str(args.get("text", "")).strip()
    if not text:
        return error_content("'text' is required.")

    voice_model = str(args.get("voice_model", "")).strip() or session.get("tts_voice", "en_US-amy-medium")

    try:
        from ..browser.media_inject import text_to_speech, setup_virtual_audio, play_audio_to_sink
    except ImportError:
        return error_content(
            "TTS requires 'piper-tts'. Install with: pip install piper-tts"
        )

    # Step 1: Generate WAV from text
    try:
        wav_path = await text_to_speech(text, voice_model=voice_model)
    except Exception as e:
        return error_content(f"TTS generation failed: {e}")

    # Step 2: Setup virtual audio sink (if not already)
    try:
        sink_info = await setup_virtual_audio()
        sink_name = sink_info.get("sink_name")
    except Exception as e:
        return error_content(f"Virtual audio setup failed: {e}")

    # Step 3: Play audio to virtual sink → browser picks it up as mic
    if sink_name:
        try:
            success = await play_audio_to_sink(wav_path, sink_name)
            if not success:
                return error_content("Audio playback to virtual sink failed.")
        except Exception as e:
            return error_content(f"Audio playback failed: {e}")
    else:
        return text_content(
            f"TTS generated at {wav_path} but no virtual audio sink available. "
            f"Install PulseAudio/PipeWire for live audio injection."
        )

    session["audio_active"] = True
    return text_content(
        f"Persona spoke: \"{text[:80]}{'...' if len(text) > 80 else ''}\"\n"
        f"  voice: {voice_model}\n"
        f"  audio: {wav_path}"
    )


# -----------------------------------------------------------------------
# teams.persona.listen
# -----------------------------------------------------------------------

async def tool_persona_listen(args: Json) -> Json:
    """Capture meeting audio and transcribe via STT."""
    sid, session = _get_session(args)
    if not sid:
        return error_content("'session_id' is required.")
    if not session:
        return error_content(f"Session {sid} not found.")

    browser = session.get("browser")
    if not browser or not browser.page:
        return error_content("Browser not active for this session.")

    duration_ms = int(args.get("duration_ms", 3000))

    # Step 1: Capture audio from browser tab
    try:
        from ..browser.media_inject import capture_tab_audio_chunk
        audio_bytes = await capture_tab_audio_chunk(browser.page, duration_ms=duration_ms)
    except Exception as e:
        return error_content(f"Audio capture failed: {e}")

    if not audio_bytes:
        return text_content("(silence — no audio captured)")

    # Step 2: Transcribe via STT pipeline (reuse existing voice infrastructure)
    audio_b64 = base64.b64encode(audio_bytes).decode()

    try:
        from ..voice.stt_pipeline import transcribe
        from ..tools.tools_voice import get_voice_state
        voice_state = get_voice_state()
        # Force enable for persona listening
        voice_state["enabled"] = True
        segments = await transcribe(audio_b64, voice_state)
    except Exception as e:
        return error_content(f"STT transcription failed: {e}")

    if not segments:
        return text_content("(silence — no speech detected)")

    lines = []
    for seg in segments:
        lines.append(f"[{seg['start']:.1f}s – {seg['end']:.1f}s] {seg['text']}")

    return text_content("\n".join(lines))


# -----------------------------------------------------------------------
# teams.persona.chat_post
# -----------------------------------------------------------------------

async def tool_persona_chat_post(args: Json) -> Json:
    """Post a message in the meeting chat via DOM automation."""
    sid, session = _get_session(args)
    if not sid:
        return error_content("'session_id' is required.")
    if not session:
        return error_content(f"Session {sid} not found.")

    text = str(args.get("text", "")).strip()
    if not text:
        return error_content("'text' is required.")

    browser = session.get("browser")
    if not browser or not browser.page:
        return error_content("Browser not active for this session.")

    success = await browser.post_chat(text)
    if success:
        return text_content(f"Posted to meeting chat: \"{text[:80]}\"")
    else:
        return error_content("Failed to post to meeting chat. Chat pane may not be accessible.")


# -----------------------------------------------------------------------
# teams.persona.chat_read
# -----------------------------------------------------------------------

async def tool_persona_chat_read(args: Json) -> Json:
    """Read recent messages from the meeting chat via DOM scraping."""
    sid, session = _get_session(args)
    if not sid:
        return error_content("'session_id' is required.")
    if not session:
        return error_content(f"Session {sid} not found.")

    browser = session.get("browser")
    if not browser or not browser.page:
        return error_content("Browser not active for this session.")

    last_n = int(args.get("last_n", 20))
    messages = await browser.read_chat(last_n=last_n)

    if not messages:
        return text_content("No messages found in chat.")

    lines = [f"Meeting chat ({len(messages)} messages):"]
    for msg in messages:
        lines.append(f"  [{msg.get('sender', '?')}]: {msg.get('content', '')}")

    return text_content("\n".join(lines))


# -----------------------------------------------------------------------
# Tool definitions
# -----------------------------------------------------------------------

TOOLS = [
    ToolDef(
        name="teams.persona.join",
        description=(
            "Join a Teams meeting as a named guest using a headless browser. "
            "No Azure registration needed — uses the anonymous guest join flow. "
            "Optionally provide a face image for the virtual camera."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "join_url": {"type": "string", "description": "Teams meeting join URL"},
                "display_name": {"type": "string", "description": "Name shown in the meeting"},
                "face_image": {"type": "string", "description": "Path to persona face image (PNG/JPG)"},
                "tts_voice": {
                    "type": "string",
                    "description": "Piper TTS voice model (default: en_US-amy-medium)",
                },
                "headless": {
                    "type": "boolean",
                    "description": "Run browser in headless mode (default: true)",
                    "default": True,
                },
            },
            "required": ["join_url", "display_name"],
        },
        handler=tool_persona_join,
    ),
    ToolDef(
        name="teams.persona.leave",
        description="Leave the Teams meeting and close the headless browser.",
        input_schema={
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Persona session ID"},
            },
            "required": ["session_id"],
        },
        handler=tool_persona_leave,
    ),
    ToolDef(
        name="teams.persona.status",
        description="Return persona session info. Omit session_id to list all active persona sessions.",
        input_schema={
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Session ID to query. Omit to list all."},
            },
        },
        handler=tool_persona_status,
    ),
    ToolDef(
        name="teams.persona.set_face",
        description=(
            "Load a static face image for the persona's virtual camera. "
            "Generates a video with subtle idle animation (sway + blink)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Persona session ID"},
                "image_path": {"type": "string", "description": "Path to face image (PNG/JPG)"},
            },
            "required": ["session_id", "image_path"],
        },
        handler=tool_persona_set_face,
    ),
    ToolDef(
        name="teams.persona.speak",
        description=(
            "Generate TTS audio from text and play it into the meeting via virtual microphone. "
            "Uses piper-tts for local, offline speech synthesis."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Persona session ID"},
                "text": {"type": "string", "description": "Text for the persona to speak"},
                "voice_model": {
                    "type": "string",
                    "description": "Piper voice model override (e.g. en_US-amy-medium)",
                },
            },
            "required": ["session_id", "text"],
        },
        handler=tool_persona_speak,
    ),
    ToolDef(
        name="teams.persona.listen",
        description=(
            "Capture meeting audio from the browser tab and transcribe using STT. "
            "Returns timestamped transcript segments. Uses the configured STT backend "
            "(Whisper by default)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Persona session ID"},
                "duration_ms": {
                    "type": "integer",
                    "description": "Duration to capture in milliseconds (default: 3000)",
                    "default": 3000,
                },
            },
            "required": ["session_id"],
        },
        handler=tool_persona_listen,
    ),
    ToolDef(
        name="teams.persona.chat_post",
        description="Post a text message in the Teams meeting chat via browser DOM automation.",
        input_schema={
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Persona session ID"},
                "text": {"type": "string", "description": "Message text to post"},
            },
            "required": ["session_id", "text"],
        },
        handler=tool_persona_chat_post,
    ),
    ToolDef(
        name="teams.persona.chat_read",
        description="Read recent messages from the Teams meeting chat via DOM scraping.",
        input_schema={
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Persona session ID"},
                "last_n": {
                    "type": "integer",
                    "description": "Number of recent messages to read (default: 20)",
                    "default": 20,
                },
            },
            "required": ["session_id"],
        },
        handler=tool_persona_chat_read,
    ),
]
