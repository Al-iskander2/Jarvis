"""
anima/mic/stt.py — Speech-to-Text local con faster-whisper
Soporta archivos y objetos file-like.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Union, BinaryIO, IO

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import config

log = logging.getLogger("jarvis.stt")

# ── Carga del modelo Whisper (singleton) ────────────────────────────────────
_WHISPER = None

def _load_whisper():
    global _WHISPER
    if _WHISPER is not None:
        return _WHISPER
    try:
        from faster_whisper import WhisperModel
        log.info(f"[STT] Cargando Whisper model='{config.WHISPER_MODEL}' compute='{config.WHISPER_COMPUTE_TYPE}'...")
        _WHISPER = WhisperModel(
            config.WHISPER_MODEL,
            device="auto",
            compute_type=config.WHISPER_COMPUTE_TYPE,
        )
        log.info("[STT] Whisper listo.")
    except ImportError:
        log.error("[STT] faster-whisper no instalado. STT no disponible.")
        _WHISPER = None
    except Exception as exc:
        log.error(f"[STT] Error cargando Whisper: {exc}")
        _WHISPER = None
    return _WHISPER


def have_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def _convert_to_wav_16k(in_path: Path, out_path: Path) -> None:
    if not have_ffmpeg():
        raise RuntimeError("ffmpeg no encontrado. Instala con: brew install ffmpeg")
    cmd = [
        "ffmpeg", "-y", "-i", str(in_path),
        "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(out_path),
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", errors="ignore"))


def transcribe_audio_local(
    audio_input: Union[str, Path, bytes, BinaryIO, IO],
    language: str = None,
) -> str:
    """
    Transcribe audio a texto.
    Acepta: ruta (str/Path), bytes, o file-like object.
    Retorna string con el texto transcrito (vacío si falla o no hay voz).
    """
    model = _load_whisper()
    if model is None:
        log.warning("[STT] Whisper no disponible, retornando texto vacío.")
        return ""

    lang = language or config.WHISPER_LANGUAGE

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # Normalizar entrada a Path
        if isinstance(audio_input, (str, Path)):
            src = Path(audio_input)
        elif isinstance(audio_input, bytes):
            src = tmp / "input.webm"
            src.write_bytes(audio_input)
        else:
            # file-like
            src = tmp / "input.webm"
            src.write_bytes(audio_input.read())

        # Convertir a WAV 16k si es posible
        wav = tmp / "input.wav"
        try:
            _convert_to_wav_16k(src, wav)
            audio_path = str(wav)
        except Exception as e:
            log.warning(f"[STT] ffmpeg no disponible ({e}), usando archivo original")
            audio_path = str(src)

        log.info(f"[STT] Transcribiendo ({lang})...")
        try:
            segments, info = model.transcribe(audio_path, language=lang, vad_filter=True)
            text = "".join(seg.text for seg in segments).strip()
            log.info(f"[STT] Transcripción: '{text[:80]}...' " if len(text) > 80 else f"[STT] '{text}'")
            return text
        except Exception as exc:
            log.error(f"[STT] Error en transcripción: {exc}")
            return ""
