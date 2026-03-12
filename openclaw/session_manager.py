import json
import hashlib
import uuid
import os
from pathlib import Path
from datetime import datetime, timezone

# We'll use a relative path for state as requested, making sure logs and state are controlled
STATE_DIR = Path(".state")
STATE_DIR.mkdir(parents=True, exist_ok=True)
SESSION_FILE = STATE_DIR / "openclaw_session.json"

class OpenClawSessionManager:
    """
    Centralizes session management, ensuring alignment between frontend, backend, and OpenClaw.
    """
    def __init__(self, logger, default_session_id: str = "voice-main"):
        self.logger = logger
        self.default_session_id = default_session_id
        self.session_data = {
            "session_id": default_session_id,
            "last_message_id": "",
            "last_user_hash": "",
            "transport": "ws",
            "state": "BOOT",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "provider": "openclaw"
        }

    def load(self, override_session_id: str = None):
        """
        Loads session from disk. If override_session_id is provided, it forces that session.
        """
        if SESSION_FILE.exists():
            try:
                with SESSION_FILE.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.session_data.update(data)
                self.logger.info("session.load.ok", session_id=self.get_session_id())
            except Exception as e:
                self.logger.error("session.load.fail", error_code="SESSION_INVALID", detail=str(e))
                self.save()
        
        if override_session_id:
            if self.session_data["session_id"] != override_session_id:
                self.logger.info("session.switch", old=self.session_data["session_id"], new=override_session_id)
                self.session_data["session_id"] = override_session_id
                # Reset idempotency markers on session switch to be safe
                self.session_data["last_message_id"] = ""
                self.session_data["last_user_hash"] = ""
                self.save()

        return self.session_data

    def save(self):
        self.session_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        try:
            with SESSION_FILE.open("w", encoding="utf-8") as f:
                json.dump(self.session_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.logger.error("session.save.fail", detail=str(e))

    def update_state(self, new_state: str, transport: str = None):
        self.session_data["state"] = new_state
        if transport:
            self.session_data["transport"] = transport
        self.save()

    def generate_message_id(self, user_text: str) -> tuple[str, str, bool]:
        """
        Unified method to track messages and prevent loops/duplicates.
        """
        text_hash = "sha256:" + hashlib.sha256(user_text.encode("utf-8")).hexdigest()
        is_duplicate = (self.session_data["last_user_hash"] == text_hash)
        
        if is_duplicate:
            self.logger.warn("message.duplicate", detail="Suppressed duplicate message", hash=text_hash)
            return self.session_data["last_message_id"], text_hash, True
            
        new_id = str(uuid.uuid4())
        self.session_data["last_message_id"] = new_id
        self.session_data["last_user_hash"] = text_hash
        self.save()
        
        return new_id, text_hash, False

    def get_session_id(self) -> str:
        return self.session_data.get("session_id", self.default_session_id)

    def get_status_summary(self):
        """
        Standardized status for API consumption.
        """
        return {
            "status": self.session_data["state"],
            "provider": self.session_data["provider"],
            "session_id": self.get_session_id(),
            "ready": self.session_data["state"] == "READY",
            "transport": self.session_data["transport"],
            "error": None # FSM will populate if needed
        }