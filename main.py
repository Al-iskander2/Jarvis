import asyncio
import base64
import os
import time
from fastapi import FastAPI, Request, File, UploadFile, Form
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from openclaw.logging_json import JsonLogger
from openclaw.session_manager import OpenClawSessionManager
from openclaw.state_machine import BridgeStateMachine, State
from openclaw.diagnostics import Diagnostics

from anima.mic.stt import transcribe_audio_local
from anima.voice.tts import synthesize_tts_edge_async

app = FastAPI(title="OpenClaw Bridge API")

logger = JsonLogger()
session_manager = OpenClawSessionManager(logger)
fsm = BridgeStateMachine(logger, session_manager)

# Ensure static directory exists and mount it
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.on_event("startup")
async def startup_event():
    logger.info("bridge.startup.init")
    # Load previous session state if any
    session_manager.load()
    # Execute full FSM boot sequence (Gateway -> Auth -> WS -> Prewarm)
    asyncio.create_task(fsm.run())

@app.get("/")
async def root():
    if not os.path.exists("jarvis.html"):
        logger.warn("ui.not_found", detail="jarvis.html missing")
        return {"error": "UI file not found"}
    return FileResponse("jarvis.html")

@app.get("/health")
async def health():
    return {
        "ok": fsm.state == State.READY,
        "state": fsm.state.value,
        "last_error": fsm.last_error
    }

@app.get("/state")
async def state_endpoint(session_id: str = None):
    # If caller provides a session_id, we align to it
    data = session_manager.load(override_session_id=session_id)
    return session_manager.get_status_summary()

async def _process_message(text: str, session_id: str = None):
    """
    Core pipeline: Text -> OpenClaw -> TTS
    """
    logger.info("message.processing.start", text=text[:50], session_id=session_id)
    
    # 1. Send to Bridge (FSM handles transport and session alignment)
    res = await fsm.send_message(text, session_id=session_id)
    
    if not res.get("ok"):
        logger.error("bridge.message.fail", detail=res.get("detail"))
        return {"ok": False, "error": res.get("detail"), "reply_text": "Error de comunicación con el cerebro."}
        
    data = res.get("data", {})
    reply_text = data.get("text", "")
    
    if not reply_text:
        # Fallback for different payload structures
        reply_text = data.get("response", {}).get("text", "Sin respuesta.")
    
    logger.info("bridge.message.response", text=reply_text[:50])

    # 2. TTS Generation
    logger.info("tts.start")
    audio_bytes, mime_type = await synthesize_tts_edge_async(reply_text)
    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8") if audio_bytes else ""
    logger.info("tts.complete", size=len(audio_bytes))
    
    return {
        "ok": True,
        "reply_text": reply_text,
        "audio_base64": audio_b64,
        "audio_mime": mime_type,
        "session_id": session_id or session_manager.get_session_id()
    }

@app.post("/chat")
async def chat(req: Request):
    try:
        data = await req.json()
        text = data.get("text", "")
        session_id = data.get("session_id")
        
        if not text:
             return {"ok": False, "error": "No message provided"}
             
        return await _process_message(text, session_id=session_id)
    except Exception as e:
        logger.error("chat.error", detail=str(e))
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

@app.post("/voice")
async def voice(audio: UploadFile = File(...), session_id: str = Form(None)):
    try:
        audio_bytes = await audio.read()
        logger.info("voice.incoming", size=len(audio_bytes), session_id=session_id)
        
        # 1. STT
        transcript = transcribe_audio_local(audio_bytes)
        if not transcript:
            logger.warn("voice.stt.empty")
            return {"ok": False, "error": "No se detectó voz."}
        
        logger.info("voice.stt.result", text=transcript)
            
        # 2. Process
        resp = await _process_message(transcript, session_id=session_id)
        return {**resp, "transcript": transcript}
    except Exception as e:
        logger.error("voice.error", detail=str(e))
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

@app.post("/abort/{session_id}")
async def abort_session(session_id: str):
    logger.info("session.abort", session_id=session_id)
    res = await fsm.abort(session_id)
    return {"ok": res.ok}

@app.post("/clear/{session_id}")
async def clear_session(session_id: str):
    logger.info("session.clear", session_id=session_id)
    # Align and reset
    session_manager.load(override_session_id=session_id)
    session_manager.session_data["last_message_id"] = ""
    session_manager.session_data["last_user_hash"] = ""
    session_manager.save()
    return {"ok": True}

@app.get("/speak")
async def speak(text: str = ""):
    audio_bytes, mime_type = await synthesize_tts_edge_async(text)
    return Response(content=audio_bytes, media_type=mime_type)
