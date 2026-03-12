"""
anima/pipeline.py — Pipeline principal de JARVIS (nombre correcto)
Orquesta: STT → LLM (con router) → TTS
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union, BinaryIO, List, Dict

log = logging.getLogger("jarvis.pipeline")

Message = Dict[str, str]


@dataclass
class PipelineResult:
    transcript: str       # Lo que dijo el usuario (STT)
    reply_text: str       # Respuesta del LLM
    reply_audio: bytes    # Audio TTS
    reply_mime: str       # MIME type del audio
    provider: str = ""    # LLM que respondió (deepseek/ollama/fallback)


async def run_pipeline_async(
    audio_input: Union[str, Path, bytes, BinaryIO],
    history: Optional[List[Message]] = None,
    session_id: str = "",
) -> PipelineResult:
    """
    Pipeline completo (async):
    1. STT: audio → texto
    2. LLM: texto → respuesta
    3. TTS: respuesta → audio bytes
    """
    from anima.mic.stt import transcribe_audio_local
    from anima.llm.router import get_router
    from anima.voice.tts import synthesize_tts_edge_async

    # ── 1. STT ──────────────────────────────────────────────────────────────
    log.info(f"[Pipeline] STT iniciando (session={session_id})")
    transcript = transcribe_audio_local(audio_input)

    if not transcript:
        msg = "No escuché nada claro. ¿Puedes intentarlo de nuevo?"
        log.info("[Pipeline] Transcripción vacía — respondiendo genérico.")
        audio, mime = await synthesize_tts_edge_async(msg)
        return PipelineResult("", msg, audio, mime, "fallback")

    # ── 2. LLM ──────────────────────────────────────────────────────────────
    router = get_router()
    messages = router.build_messages(transcript, history=history)
    reply_text, provider = router.chat(messages)
    log.info(f"[Pipeline] LLM ({provider}): '{reply_text[:60]}...'")

    # ── 3. TTS ──────────────────────────────────────────────────────────────
    audio, mime = await synthesize_tts_edge_async(reply_text)
    log.info(f"[Pipeline] TTS: {len(audio)} bytes")

    return PipelineResult(
        transcript=transcript,
        reply_text=reply_text,
        reply_audio=audio,
        reply_mime=mime,
        provider=provider,
    )


def run_pipeline(
    audio_input: Union[str, Path, bytes, BinaryIO],
    extra_context: Optional[str] = None,
    history: Optional[List[Message]] = None,
    session_id: str = "",
) -> PipelineResult:
    """
    Versión blocking (para compatibilidad con pipline.py original).
    """
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(
            run_pipeline_async(audio_input, history=history, session_id=session_id)
        )
    finally:
        loop.close()
    return result
