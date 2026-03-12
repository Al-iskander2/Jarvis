from __future__ import annotations
import asyncio
import base64
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
import websockets
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key

_WS_HEADERS = {
    "Origin": "http://127.0.0.1:18789",
    "User-Agent": "openclaw-control-ui",
}

_IDENTITY_PATH = Path.home() / ".openclaw" / "identity" / "device.json"
_CONFIG_PATH = Path.home() / ".openclaw" / "openclaw.json"

def _get_gateway_token():
    try:
        data = json.loads(_CONFIG_PATH.read_text())
        return data.get("gateway", {}).get("auth", {}).get("token")
    except Exception:
        return None

def _load_identity():
    try:
        data = json.loads(_IDENTITY_PATH.read_text())
        device_id = data["deviceId"]
        priv_pem = data["privateKeyPem"].encode()
        private_key = load_pem_private_key(priv_pem, password=None)
        pub_lines = [l for l in data["publicKeyPem"].split("\n") if l and not l.startswith("---")]
        pub_der = base64.b64decode("".join(pub_lines))
        pub_raw = pub_der[-32:]
        pub_b64url = base64.urlsafe_b64encode(pub_raw).rstrip(b"=").decode("utf-8")
        return device_id, pub_b64url, private_key
    except Exception:
        return None, None, None

def _build_signature(private_key, device_id, nonce, signed_at_ms, token=""):
    scopes = "operator.admin,operator.read,operator.write,operator.approvals,operator.pairing"
    payload = "|".join(["v2", device_id, "cli", "cli", "operator", scopes, str(signed_at_ms), token or "", nonce])
    signature = private_key.sign(payload.encode("utf-8"))
    return base64.urlsafe_b64encode(signature).rstrip(b"=").decode("utf-8")

@dataclass
class WSResult:
    ok: bool
    latency_ms: int
    data: dict | None = None
    error_code: str | None = None
    detail: str | None = None

class OpenClawWSTransport:
    def __init__(self, ws_url: str, logger, timeout: float = 60.0):
        self.ws_url = ws_url
        self.logger = logger
        self.timeout = timeout
        self.ws = None
        self._device_id, self._pub_b64url, self._private_key = _load_identity()
        self._gateway_token = _get_gateway_token()
        self._rpc_futures: dict[str, asyncio.Future] = {}
        self._chat_queues: dict[str, asyncio.Queue] = {}
        self._pending_chat_events: dict[str, list] = {}
        self._listener_task = None
        self._lock = asyncio.Lock()

    def _is_open(self) -> bool:
        if self.ws is None: return False
        state = getattr(self.ws, "state", None)
        if state is None: return False
        return str(state) == "OPEN" or getattr(state, "name", "") == "OPEN"

    async def connect(self) -> WSResult:
        async with self._lock:
            if self._is_open(): return WSResult(True, 0)
            started = time.perf_counter()
            try:
                self.logger.info("ws.connect.start", transport="ws")
                if self._listener_task: 
                     self._listener_task.cancel()
                     self._listener_task = None
                
                ws = await asyncio.wait_for(websockets.connect(self.ws_url, additional_headers=_WS_HEADERS), timeout=15.0)
                raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                challenge = json.loads(raw)
                nonce = challenge["payload"]["nonce"]
                
                signed_at = int(time.time() * 1000)
                token = self._gateway_token or ""
                signature = _build_signature(self._private_key, self._device_id, nonce, signed_at, token)
                
                req_id = str(uuid.uuid4())
                connect_req = {
                    "type": "req", "id": req_id, "method": "connect",
                    "params": {
                        "minProtocol": 3, "maxProtocol": 3,
                        "client": {"id": "cli", "mode": "cli", "platform": "darwin", "version": "1.0"},
                        "role": "operator",
                        "scopes": ["operator.admin", "operator.read", "operator.write", "operator.approvals", "operator.pairing"],
                        "auth": {"token": token},
                        "device": {"id": self._device_id, "publicKey": self._pub_b64url, "signature": signature, "nonce": nonce, "signedAt": signed_at}
                    }
                }
                await ws.send(json.dumps(connect_req))
                
                while True:
                    raw_res = await asyncio.wait_for(ws.recv(), timeout=10.0)
                    res = json.loads(raw_res)
                    if res.get("id") == req_id:
                        if res.get("ok"):
                            self.ws = ws
                            self._start_listener()
                            latency = int((time.perf_counter() - started) * 1000)
                            self.logger.info("ws.connect.ok", transport="ws")
                            return WSResult(True, latency)
                        else:
                            raise ValueError(f"Handshake failed: {res.get('error')}")
            except Exception as e:
                self.logger.error("ws.connect.fail", transport="ws", detail=str(e))
                return WSResult(False, 0, error_code="WS_CONNECT_ERROR", detail=str(e))

    def _start_listener(self):
        self._listener_task = asyncio.create_task(self._listen_loop())

    async def _listen_loop(self):
        try:
            async for raw in self.ws:
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    self.logger.warn("ws.listener.invalid_json", raw=raw, transport="ws")
                    continue # Skip this message if it's not valid JSON
                
                if not isinstance(data, dict):
                    self.logger.warn("ws.listener.non_dict_data", data_type=type(data), transport="ws")
                    continue # Skip if data is not a dictionary
                
                itid = data.get("id")
                if data.get("type") == "res" and isinstance(itid, str) and itid in self._rpc_futures:
                    fut = self._rpc_futures.pop(itid)
                    if not fut.done(): fut.set_result(data)
                elif data.get("type") == "event" and data.get("event") == "chat":
                    payload = data.get("payload", {})
                    run_id = payload.get("runId")
                    if not run_id:
                        continue
                        
                    self.logger.info("chat.event.received", run_id=run_id, transport="ws")
                    if run_id in self._chat_queues:
                        await self._chat_queues[run_id].put(data)
                    else:
                        self.logger.info("chat.event.buffered", run_id=run_id, transport="ws")
                        self._pending_chat_events.setdefault(run_id, []).append(data)
        except Exception:
            pass
        finally:
            self.ws = None
            for fut in list(self._rpc_futures.values()):
                if not fut.done(): fut.set_exception(ConnectionError("WS closed"))
            self._rpc_futures.clear()

    async def rpc(self, method: str, params: dict) -> WSResult:
        if not self._is_open():
            conn = await self.connect()
            if not conn.ok: return WSResult(False, conn.latency_ms, error_code=conn.error_code, detail=conn.detail)
            
        started = time.perf_counter()
        req_id = str(uuid.uuid4())
        fut = asyncio.get_running_loop().create_future()
        self._rpc_futures[req_id] = fut
        try:
            await self.ws.send(json.dumps({"type": "req", "id": req_id, "method": method, "params": params}))
            data = await asyncio.wait_for(fut, timeout=self.timeout)
            latency = int((time.perf_counter() - started) * 1000)
            if data.get("ok"):
                return WSResult(True, latency, data=data.get("payload"))
            else:
                return WSResult(False, latency, error_code="RPC_ERROR", detail=str(data.get("error")))
        except Exception as e:
            self._rpc_futures.pop(req_id, None)
            return WSResult(False, 0, error_code="WS_RPC_FAILED", detail=str(e))

    async def send_chat(self, session_id: str, text: str, message_id: str) -> WSResult:
        self.logger.info("chat.send.accepted", session_id=session_id, message_id=message_id, transport="ws")
        started = time.perf_counter()
        res = await self.rpc("chat.send", {"sessionKey": session_id, "message": text, "idempotencyKey": message_id})
        if not res.ok: return res
        run_id = res.data.get("runId")
        if not run_id: return res
        
        queue = asyncio.Queue()
        self._chat_queues[run_id] = queue

        # flush buffered events
        if run_id in self._pending_chat_events:
            for ev in self._pending_chat_events.pop(run_id):
                await queue.put(ev)

        try:
            deadline = time.perf_counter() + self.timeout
            while True:
                remaining = deadline - time.perf_counter()
                if remaining <= 0: raise asyncio.TimeoutError("Wait for final chat event timeout")
                data = await asyncio.wait_for(queue.get(), timeout=remaining)
                if not data:
                    continue
                payload = data.get("payload", {})
                if payload.get("state") == "final":
                    self.logger.info("chat.final.received", run_id=run_id, session_id=session_id, message_id=message_id, transport="ws")
                    latency_ms = int((time.perf_counter() - started) * 1000)
                    # Extract text from complex message structure
                    msg = payload.get("message", {})
                    text_out = ""
                    if isinstance(msg, dict):
                        content = msg.get("content", [])
                        if isinstance(content, list) and len(content) > 0:
                            # Assume first text part is dominant for voice
                            text_out = " ".join([block.get("text", "") for block in content if block.get("type") == "text"])
                        elif "text" in msg:
                            text_out = msg["text"]
                    elif isinstance(msg, str):
                        text_out = msg
                    
                    self.logger.info("ws.chat.ok", transport="ws", latency_ms=latency_ms, run_id=run_id, session_id=session_id, message_id=message_id)
                    return WSResult(True, latency_ms, data={"text": text_out, "runId": run_id})
                elif payload.get("state") == "error":
                    raise ValueError(payload.get("errorMessage", "Unknown error in chat stream"))
        except asyncio.TimeoutError:
            self.logger.warn("ws.chat.timeout", transport="ws", run_id=run_id, session_id=session_id, message_id=message_id, timeout_phase="waiting_for_final")
            hist_res = await self.history(session_id, limit=3)
            if hist_res.ok and hist_res.data:
                items = hist_res.data.get("items", []) if isinstance(hist_res.data, dict) else hist_res.data
                if isinstance(items, list):
                    for item in items: # Assuming history is returning most recent first or we check all recent
                        if item.get("role") == "assistant" or item.get("author", {}).get("role") == "assistant":
                            msg = item.get("message", item.get("content", ""))
                            text_out = ""
                            if isinstance(msg, dict):
                                content = msg.get("content", [])
                                if isinstance(content, list) and len(content) > 0:
                                    text_out = " ".join([block.get("text", "") for block in content if block.get("type") == "text"])
                                elif "text" in msg:
                                    text_out = msg["text"]
                            elif isinstance(msg, str):
                                text_out = msg
                            
                            if text_out:
                                self.logger.info("chat.final.recovered_from_history", transport="ws", run_id=run_id, session_id=session_id, message_id=message_id)
                                latency_ms = int((time.perf_counter() - started) * 1000)
                                return WSResult(True, latency_ms, data={"text": text_out, "runId": run_id})
            return WSResult(False, 0, error_code="CHAT_WAIT_TIMEOUT", detail="Wait for final chat event timeout")
        except Exception as e:
            self.logger.error("ws.chat.fail", transport="ws", detail=str(e), run_id=run_id, session_id=session_id, message_id=message_id)
            return WSResult(False, 0, error_code="CHAT_WAIT_FAILED", detail=str(e))
        finally:
            self._chat_queues.pop(run_id, None)
            self._pending_chat_events.pop(run_id, None)


    async def history(self, session_id: str, limit: int = 10) -> WSResult:
        return await self.rpc("chat.history", {"sessionKey": session_id, "limit": limit})

    async def abort(self, session_id: str) -> WSResult:
        return await self.rpc("chat.abort", {"sessionKey": session_id})
