"""Azure Communication Services (ACS) client for Teams meeting audio.

Manages the lifecycle of joining a Teams meeting as an ACS participant,
capturing mixed audio, and piping chunks to the STT pipeline.

This module provides the *interface* — actual audio capture requires
the ``azure-communication-calling`` SDK which is imported lazily.

Architecture::

    Teams Meeting
        │
        ▼  (ACS Teams interop)
    AcsClient.join(join_url)
        │
        ├── audio_stream → STT pipeline → text segments
        │
        └── AcsClient.leave()
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional

log = logging.getLogger("teams_mcp.acs.client")


@dataclass
class AcsSession:
    """Tracks the state of a single ACS meeting join."""
    session_id: str
    join_url: str
    connection_string: str
    status: str = "pending"           # pending | joining | connected | capturing | disconnected | error
    connected_at: Optional[float] = None
    error: Optional[str] = None
    audio_chunks_captured: int = 0
    transcripts: List[Dict[str, Any]] = field(default_factory=list)


# In-process session registry
_acs_sessions: Dict[str, AcsSession] = {}
_session_counter: int = 0


def get_sessions() -> Dict[str, AcsSession]:
    """Return the sessions dict (for testing)."""
    return _acs_sessions


async def acs_join(
    join_url: str,
    connection_string: str,
    on_audio_chunk: Optional[Callable[[bytes], Coroutine[Any, Any, None]]] = None,
) -> AcsSession:
    """Join a Teams meeting via ACS and start audio capture.

    Parameters
    ----------
    join_url:
        Teams meeting join URL.
    connection_string:
        ACS connection string (from Azure Portal).
    on_audio_chunk:
        Optional async callback invoked with each captured audio chunk.

    Returns
    -------
    AcsSession
        The session tracking object.

    Notes
    -----
    This is a *scaffold* implementation.  Full audio capture requires:

    1. ``azure-communication-calling`` SDK
    2. An ACS resource provisioned in Azure with Teams interop enabled
    3. The ACS resource must have PSTN or direct routing (for bot dial-in)
       OR use the Teams interop gateway

    The actual integration follows this pattern::

        from azure.communication.calling import CallClient, CallAgent
        call_client = CallClient()
        token_credential = CommunicationTokenCredential(user_token)
        call_agent = call_client.create_call_agent(token_credential)
        join_call_options = JoinCallOptions(audio_options=AudioOptions(muted=True))
        call = call_agent.join(TeamsMeetingLinkLocator(join_url), join_call_options)
        call.on('stateChanged', handle_state)
        remote_audio_stream = call.remote_audio_streams[0]
        # Pipe remote_audio_stream to on_audio_chunk callback
    """
    global _session_counter
    _session_counter += 1
    session_id = f"acs-{int(time.time() * 1000)}-{_session_counter}"

    session = AcsSession(
        session_id=session_id,
        join_url=join_url,
        connection_string=connection_string,
        status="pending",
    )
    _acs_sessions[session_id] = session

    # Attempt to load the ACS SDK
    try:
        # Phase 1: Validate the connection string format
        if not connection_string.startswith("endpoint="):
            session.status = "error"
            session.error = (
                "Invalid ACS connection string format.  "
                "Expected: 'endpoint=https://<resource>.communication.azure.com/;accesskey=...'"
            )
            return session

        session.status = "joining"
        log.info("ACS join requested: session=%s  url=%s", session_id, join_url[:80])

        # In a full implementation, this is where we would:
        # 1. Create a CommunicationIdentityClient from the connection string
        # 2. Generate a user token with VoIP scope
        # 3. Create a CallAgent
        # 4. Join the meeting using TeamsMeetingLinkLocator
        # 5. Start capturing remote audio stream
        #
        # For now, we mark the session as "pending_sdk" — the ACS calling SDK
        # is not yet wired.  This scaffold validates config + tracks state.

        session.status = "pending_sdk"
        session.connected_at = time.time()
        log.info(
            "ACS session %s created (pending_sdk — azure-communication-calling not wired yet)",
            session_id,
        )

    except Exception as exc:
        session.status = "error"
        session.error = str(exc)
        log.exception("ACS join failed: %s", exc)

    return session


async def acs_leave(session_id: str) -> Optional[AcsSession]:
    """Leave an ACS meeting session.

    Returns the session if found, None otherwise.
    """
    session = _acs_sessions.get(session_id)
    if not session:
        return None

    log.info("ACS leave: session=%s  status=%s", session_id, session.status)

    # In a full implementation: call_agent.hangup(), dispose resources
    session.status = "disconnected"
    return session


async def acs_status(session_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return status of one or all ACS sessions."""
    if session_id:
        session = _acs_sessions.get(session_id)
        if not session:
            return []
        return [_session_to_dict(session)]

    return [_session_to_dict(s) for s in _acs_sessions.values()]


def _session_to_dict(s: AcsSession) -> Dict[str, Any]:
    return {
        "session_id": s.session_id,
        "join_url": s.join_url,
        "status": s.status,
        "connected_at": s.connected_at,
        "error": s.error,
        "audio_chunks_captured": s.audio_chunks_captured,
        "transcripts_count": len(s.transcripts),
    }
