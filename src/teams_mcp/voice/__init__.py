"""Voice / speech-to-text pipeline package.

Provides pluggable STT backends (Whisper, Deepgram, Azure Speech) behind
a unified ``transcribe()`` async interface.  All backends are optional —
import errors are deferred until the backend is actually selected.
"""
