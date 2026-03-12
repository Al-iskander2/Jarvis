import argparse
import asyncio
import json
import os
import sys

from .logging_json import JsonLogger
from .diagnostics import Diagnostics
from .session_manager import OpenClawSessionManager
from .state_machine import BridgeStateMachine, State

def cmd_status(args):
    logger = JsonLogger()
    diag = Diagnostics(logger)
    sm = OpenClawSessionManager(logger)
    res = diag.check_health()
    state = sm.load().get("state", "UNKNOWN")
    out = {"health_ok": res, "state": state}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if not res or state == "FAILED":
        sys.exit(1)

def cmd_doctor(args):
    logger = JsonLogger()
    diag = Diagnostics(logger)
    res = diag.run_cmd(["openclaw", "doctor"])
    print(json.dumps(res, ensure_ascii=False, indent=2))
    if "error" in res:
        sys.exit(1)

async def _prewarm(args):
    logger = JsonLogger()
    sm = OpenClawSessionManager(logger)
    sm.load()
    if args.session:
        sm.session_data["session_id"] = args.session
        sm.save()
        
    fsm = BridgeStateMachine(logger, sm)
    await fsm.run()
    
    if fsm.state == State.READY:
        print(json.dumps({"ok": True, "session_id": sm.get_session_id(), "state": "READY"}, ensure_ascii=False))
        sys.exit(0)
    else:
        print(json.dumps({"ok": False, "session_id": sm.get_session_id(), "state": fsm.state.value}, ensure_ascii=False))
        sys.exit(2)

def cmd_prewarm(args):
    asyncio.run(_prewarm(args))

def cmd_send(args):
    # Sends a message ad-hoc using StateMachine
    logger = JsonLogger()
    sm = OpenClawSessionManager(logger)
    sm.load()
    if args.session:
        sm.session_data["session_id"] = args.session
        sm.save()
        
    fsm = BridgeStateMachine(logger, sm)
    async def _send():
        # we try direct hook logic since we're invoked as one-shot CLI or via FSM connect
        # If State != READY, just use hook or we do a quick connect
        await fsm.ws.connect()
        fsm.state = State.READY
        res = await fsm.send_message(args.message)
        print(json.dumps(res))
    asyncio.run(_send())

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("status")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("doctor")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("prewarm")
    p.add_argument("--session", default=os.getenv("OPENCLAW_SESSION_ID", "voice-main"))
    p.set_defaults(func=cmd_prewarm)

    p = sub.add_parser("send")
    p.add_argument("--session", default="voice-main")
    p.add_argument("--message", required=True)
    p.set_defaults(func=cmd_send)

    args = ap.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()