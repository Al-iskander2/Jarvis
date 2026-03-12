import asyncio
import os
import time
from enum import Enum
from .logging_json import JsonLogger
from .diagnostics import Diagnostics
from .session_manager import OpenClawSessionManager
from .transport_ws import OpenClawWSTransport
from .transport_hook import OpenClawHookTransport
from .retry import RetryManager

class State(Enum):
    BOOT = "BOOT"
    PREFLIGHT = "PREFLIGHT"
    GATEWAY_READY = "GATEWAY_READY"
    WS_CONNECTING = "WS_CONNECTING"
    WS_READY = "WS_READY"
    SESSION_PREWARM = "SESSION_PREWARM"
    READY = "READY"
    DEGRADED = "DEGRADED"
    RECOVERING = "RECOVERING"
    FAILED = "FAILED"

class BridgeStateMachine:
    def __init__(self, logger: JsonLogger, sm: OpenClawSessionManager):
        self.logger = logger
        self.sm = sm
        self.state = State.BOOT
        self.diag = Diagnostics(self.logger)
        self.last_error = None
        
        ws_url = os.getenv("OPENCLAW_WS_URL", "ws://127.0.0.1:18789/")
        
        self.ws = OpenClawWSTransport(ws_url, self.logger)
        self.retry = RetryManager(self.logger)

        self.sm.update_state(self.state.value)

    def transition(self, new_state: State, error=None):
        self.logger.info("state.transition", detail=f"{self.state.value} -> {new_state.value}", state=new_state.value, error=error)
        self.state = new_state
        self.last_error = error
        self.sm.update_state(self.state.value)

    async def run(self):
        """
        Main boot sequence: Preflight -> Gateway -> WS -> Prewarm -> Ready
        """
        self.logger.info("bridge.boot", session_id=self.sm.get_session_id())
        
        # 1. Preflight
        self.transition(State.PREFLIGHT)
        diag_ok = self.diag.check_health()
        if not diag_ok:
            self.transition(State.FAILED, "Gateway status check failed")
            return
            
        self.transition(State.GATEWAY_READY)

        # 2. WS Connect + Prewarm
        await self._ensure_ready()

    async def _ensure_ready(self):
        # WS Connection
        self.transition(State.WS_CONNECTING)
        res = await self.ws.connect()
        if not res.ok:
            self.logger.error("bridge.ws.fail", detail=res.detail, error_code=res.error_code)
            self.transition(State.DEGRADED, res.detail)
            return

        self.transition(State.WS_READY)
        
        # Session Prewarm (Strictly required for State.READY)
        self.transition(State.SESSION_PREWARM)
        sid = self.sm.get_session_id()
        hist = await self.ws.history(sid, limit=1)
        if hist.ok:
            self.logger.info("bridge.ready", session_id=sid)
            self.transition(State.READY)
        else:
            self.logger.error("bridge.prewarm.fail", error_code=hist.error_code, detail=hist.detail)
            self.transition(State.DEGRADED, f"Prewarm failed: {hist.detail}")

    async def reconnect_ws(self):
        self.transition(State.RECOVERING)
        self.logger.info("ws.reconnect.start", transport="ws")
        if self.ws.ws:
            try:
                await self.ws.ws.close()
            except Exception:
                pass
        
        res = await self.ws.connect()
        if res.ok:
            self.logger.info("ws.reconnect.success", transport="ws")
            sid = self.sm.get_session_id()
            hist = await self.ws.history(sid, limit=1)
            if hist.ok:
                self.transition(State.READY)
                return True
        
        self.transition(State.DEGRADED)
        return False

    async def send_message(self, text: str, session_id: str = None) -> dict:
        """
        Sends message using the best available transport.
        """
        if session_id:
            # Sync session if requested by caller
            self.sm.load(override_session_id=session_id)

        msg_id, text_hash, is_dup = self.sm.generate_message_id(text)
        current_sid = self.sm.get_session_id()
        
        if is_dup:
            return {"ok": True, "detail": "suppressed duplicate"}

        self.logger.info("message.incoming", session_id=current_sid, text=text[:50])
        
        for attempt in range(2):
            if self.state in (State.READY, State.RECOVERING):
                self.logger.info("bridge.ws.send", session_id=current_sid, attempt=attempt+1)
                
                state_before = self.state.value
                start_ts = time.perf_counter()
                
                # set state for logging in transport
                self.ws._state_for_log = state_before
                
                res = await self.ws.send_chat(current_sid, text, msg_id)
                latency = int((time.perf_counter() - start_ts) * 1000)
                
                run_id = res.data.get("runId") if res.data else None
                state_after = self.state.value

                if attempt == 0 and not res.ok:
                    self.logger.warn("bridge.ws.fallback", detail=res.detail, attempt=attempt+1, session_id=current_sid, message_id=msg_id, run_id=run_id, transport="ws", state_before=state_before, state_after=state_after)
                    recon_success = await self.reconnect_ws()
                    if not recon_success:
                        self.transition(State.DEGRADED, res.detail)
                        break
                elif res.ok:
                    self.logger.info("bridge.ws.recv", latency_ms=latency, session_id=current_sid, message_id=msg_id, run_id=run_id, transport="ws", state_before=state_before, state_after=state_after)
                    return {"ok": True, "data": res.data}
                else:
                    self.logger.error("bridge.ws.fail_final", detail=res.detail, attempt=attempt+1, session_id=current_sid, message_id=msg_id, run_id=run_id, transport="ws", state_before=state_before, state_after=state_after)
                    self.transition(State.DEGRADED, res.detail)

        return {"ok": False, "error_code": res.error_code if 'res' in locals() and res else "TRANSPORT_FAILED", "detail": res.detail if 'res' in locals() and res else "All WebSocket attempts failed."}

    async def abort(self, session_id: str):
        self.logger.info("bridge.abort", session_id=session_id)
        return await self.ws.abort(session_id)
