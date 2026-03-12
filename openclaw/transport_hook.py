import time
import requests
from dataclasses import dataclass

@dataclass
class HookResult:
    ok: bool
    latency_ms: int
    data: dict | None = None
    error_code: str | None = None
    detail: str | None = None

class OpenClawHookTransport:
    def __init__(self, hook_url: str, logger, timeout: float = 15.0):
        self.hook_url = hook_url
        self.logger = logger
        self.timeout = timeout

    def send_chat(self, session_id: str, text: str, message_id: str) -> HookResult:
        started = time.perf_counter()
        
        payload = {
            "sessionKey": session_id,
            "text": text,
            "clientMessageId": message_id
        }
        
        try:
            self.logger.info("hook.send.start", transport="hook", detail=self.hook_url)
            resp = requests.post(self.hook_url, json=payload, timeout=self.timeout)
            latency = int((time.perf_counter() - started) * 1000)
            
            if resp.status_code == 200:
                self.logger.info("hook.send.ok", transport="hook", latency_ms=latency)
                try:
                    data = resp.json()
                    return HookResult(True, latency, data=data)
                except Exception:
                    return HookResult(True, latency, data={"raw": resp.text})
            elif resp.status_code == 401:
                self.logger.error("hook.send.fail", transport="hook", latency_ms=latency, error_code="HOOK_HTTP_401")
                return HookResult(False, latency, error_code="HOOK_HTTP_401", detail="Unauthorized")
            elif resp.status_code == 403:
                self.logger.error("hook.send.fail", transport="hook", latency_ms=latency, error_code="HOOK_HTTP_403")
                return HookResult(False, latency, error_code="HOOK_HTTP_403", detail="Forbidden")
            else:
                err_code = f"HOOK_HTTP_{resp.status_code}" if resp.status_code >= 500 else "HOOK_SESSIONKEY_REJECTED"
                if resp.status_code == 400 and "sessionKey" in resp.text:
                    err_code = "HOOK_SESSIONKEY_REJECTED"
                self.logger.error("hook.send.fail", transport="hook", latency_ms=latency, error_code=err_code, detail=resp.text)
                return HookResult(False, latency, error_code=err_code, detail=resp.text)
                
        except requests.exceptions.Timeout:
            latency = int((time.perf_counter() - started) * 1000)
            self.logger.error("hook.send.fail", transport="hook", latency_ms=latency, error_code="HOOK_HTTP_TIMEOUT")
            return HookResult(False, latency, error_code="HOOK_HTTP_TIMEOUT", detail="Timeout")
        except Exception as e:
            latency = int((time.perf_counter() - started) * 1000)
            self.logger.error("hook.send.fail", transport="hook", latency_ms=latency, error_code="HOOK_HTTP_ERROR", detail=str(e))
            return HookResult(False, latency, error_code="HOOK_HTTP_ERROR", detail=str(e))
