"""
anima/voice/tts.py — Text-to-Speech con Edge-TTS
Compatible con edge-tts ≥ 6.x y 7.x (usa streaming, no .save()).
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Tuple

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import config

log = logging.getLogger("jarvis.tts")


async def _tts_stream_bytes(text: str, voice: str) -> bytes:
    """
    Genera audio vía edge_tts usando streaming (compatible v6 y v7).
    Retorna los bytes crudos del audio MP3/WAV.
    """
    import edge_tts

    communicate = edge_tts.Communicate(text, voice)
    audio_data = b""

    try:
        # API v7+: communicate.stream() es async generator
        async for chunk in communicate.stream():
            if chunk.get("type") == "audio":
                audio_data += chunk["data"]
    except AttributeError:
        # Fallback API v6: communicate.run() llena el buffer internamente
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "speech.mp3"
            await communicate.save(str(out))
            audio_data = out.read_bytes()

    return audio_data


async def synthesize_tts_edge_async(
    text: str,
    voice: str = None,
    fmt: str = None,
) -> Tuple[bytes, str]:
    """
    TTS async — para usar directamente en endpoints FastAPI.
    Retorna (audio_bytes, mime_type).
    """
    v = voice or config.EDGE_TTS_VOICE
    f = fmt or config.EDGE_TTS_FORMAT

    if not text or not text.strip():
        log.warning("[TTS] Texto vacío, retornando audio vacío.")
        return b"", "audio/mpeg"

    try:
        audio = await _tts_stream_bytes(text.strip(), v)
        log.info(f"[TTS] ✓ {len(audio)} bytes (voice={v})")
        if len(audio) < 100:
            log.warning(f"[TTS] Audio sospechosamente pequeño: {len(audio)} bytes")
    except Exception as exc:
        log.error(f"[TTS] Error: {exc}")
        audio = b""

    mime = "audio/mpeg" if f.lower() == "mp3" else "audio/wav"
    return audio, mime


def synthesize_tts_edge(
    text: str,
    voice: str = None,
    fmt: str = None,
) -> Tuple[bytes, str]:
    """
    TTS blocking — para tests o uso fuera de FastAPI.
    No llamar desde un event loop activo.
    """
    try:
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(synthesize_tts_edge_async(text, voice, fmt))
        loop.close()
        return result
    except Exception as exc:
        log.error(f"[TTS] Error blocking: {exc}")
        return b"", "audio/mpeg"
