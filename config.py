import os

# STT Config
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "tiny")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "es")

# TTS Config
EDGE_TTS_VOICE = os.getenv("EDGE_TTS_VOICE", "es-ES-AlvaroNeural")
EDGE_TTS_FORMAT = os.getenv("EDGE_TTS_FORMAT", "mp3")
