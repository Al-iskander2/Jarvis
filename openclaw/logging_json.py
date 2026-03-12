import json
import logging
import time
import os
import socket
from datetime import datetime, timezone
from pathlib import Path

# Relative paths for portability
LOGS_DIR = Path("logs")

class JsonLogger:
    def __init__(self, service="openclaw-bridge"):
        self.service = service
        self.host = socket.gethostname()
        self.pid = os.getpid()
        
        # Ensure directory structure
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        (LOGS_DIR / "sessions").mkdir(parents=True, exist_ok=True)
        (LOGS_DIR / "health").mkdir(parents=True, exist_ok=True)
        
        self.bridge_path = LOGS_DIR / "bridge.jsonl"
        self.errors_path = LOGS_DIR / "errors.jsonl"

    def _write(self, path: Path, entry: dict):
        try:
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            # Fallback to stderr if file system fails
            print(f"FAILED TO WRITE LOG TO {path}: {entry}")

    def log(self, level: str, event: str, **kwargs):
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "service": self.service,
            "host": self.host,
            "pid": self.pid,
            "event": event,
            # Extra context
            **{k: v for k, v in kwargs.items() if v is not None}
        }
        
        self._write(self.bridge_path, entry)
        
        if level in ["ERROR", "CRITICAL"]:
            self._write(self.errors_path, entry)
            
        session_id = kwargs.get("session_id")
        if session_id:
            # Clean session_id for filename safety
            safe_sid = "".join([c if c.isalnum() else "_" for c in str(session_id)])
            session_path = LOGS_DIR / "sessions" / f"{safe_sid}.jsonl"
            self._write(session_path, entry)

    def info(self, event: str, **kwargs): self.log("INFO", event, **kwargs)
    def warn(self, event: str, **kwargs): self.log("WARN", event, **kwargs)
    def error(self, event: str, **kwargs): self.log("ERROR", event, **kwargs)
    def debug(self, event: str, **kwargs): self.log("DEBUG", event, **kwargs)

    def update_health(self, filename: str, data: dict):
        path = LOGS_DIR / "health" / filename
        data["ts"] = datetime.now(timezone.utc).isoformat()
        try:
            with path.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.error("health.write.fail", detail=str(e))