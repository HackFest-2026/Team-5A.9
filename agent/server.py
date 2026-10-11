"""HTTP front for the agent, so it can be embedded in an application page.

    POST /ask     {"question": "...", "session_id": "optional"}  ->  answer, deep link, actions taken, latency
    POST /reset   {"session_id": "..."}                           ->  forget the conversation
    GET  /health                                                  ->  model, plan mode, backend, whether the data API answers

Run:  source r1.env; AGENT_PLAN_MODE=slots python -m agent.server --host 10.9.0.105 --port 8018
One question is processed at a time (the model and the agent object are shared), so a second user waits for the first.
CORS is open because the page and this service sit on different ports; the service is read-only and has no login.
"""
from __future__ import annotations

import argparse
import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx

from .cli import build_agent
from .config import Config
from .ledger import build_ledger

MAX_BODY = 4096
MAX_QUESTION = 600
MAX_SESSIONS = 200
SESSION_TTL = 3600


class Service:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.agent = build_agent(cfg)
        self.sessions: dict[str, list] = {}   # id -> [Session, last_used]
        self.lock = threading.Lock()

    def session(self, sid: str | None):
        now = time.time()
        for k in [k for k, v in self.sessions.items() if now - v[1] > SESSION_TTL]:
            del self.sessions[k]
        if sid and sid in self.sessions:
            self.sessions[sid][1] = now
            return sid, self.sessions[sid][0]
        if len(self.sessions) >= MAX_SESSIONS:
            del self.sessions[min(self.sessions, key=lambda k: self.sessions[k][1])]
        sid = uuid.uuid4().hex[:16]
        self.sessions[sid] = [self.agent.new_session(), now]
        return sid, self.sessions[sid][0]

    def ask(self, question: str, sid: str | None) -> dict:
        with self.lock:
            sid, sess = self.session(sid)
            before = sess.turns
            r = self.agent.turn(question, sess)
        return {"session_id": sid, "status": r.status, "op": r.op, "text": r.text, "notes": r.notes, "deep_link": r.deep_link,
                "actions": [a["summary"] for a in r.actions], "latency": round(r.latency, 2), "llm_calls": r.llm_calls,
                "answer_source": r.answer_source, "ledger": build_ledger(r, before > 0), "proposal": r.proposal}

    def health(self) -> dict:
        ok = False
        try:
            ok = httpx.get(self.cfg.wwi_url.rstrip("/") + "/api/capabilities", timeout=3).status_code == 200
        except httpx.HTTPError:
            pass
        return {"ok": True, "model": self.cfg.llm_model, "plan_mode": self.cfg.plan_mode, "backend": self.cfg.backend,
                "data_api": ok, "gates": self.cfg.gates}


def make_handler(svc: Service):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code: int, obj: dict):
            data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        def do_GET(self):
            if self.path.split("?")[0] == "/health":
                self._send(200, svc.health())
            else:
                self._send(404, {"error": "unknown route"})

        def do_POST(self):
            try:
                n = int(self.headers.get("Content-Length", "0"))
                if n <= 0 or n > MAX_BODY:
                    raise ValueError(f"body must be 1..{MAX_BODY} bytes")
                body = json.loads(self.rfile.read(n))
                if not isinstance(body, dict):
                    raise ValueError("body must be a JSON object")
                route = self.path.split("?")[0]
                if route == "/ask":
                    q = str(body.get("question", "")).strip()
                    if not q or len(q) > MAX_QUESTION:
                        raise ValueError(f"question must be 1..{MAX_QUESTION} characters")
                    self._send(200, svc.ask(q, body.get("session_id")))
                elif route == "/reset":
                    svc.sessions.pop(str(body.get("session_id", "")), None)
                    self._send(200, {"ok": True})
                else:
                    self._send(404, {"error": "unknown route"})
            except ValueError as e:
                self._send(422, {"status": "error", "text": str(e)})
            except Exception as e:  # the assistant must never take the page down
                self._send(500, {"status": "error", "text": f"The assistant hit an error: {type(e).__name__}. Try again."})

    return H


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8018)
    a = ap.parse_args()
    svc = Service(Config())
    print(f"agent service on http://{a.host}:{a.port}  model={svc.cfg.llm_model} plan={svc.cfg.plan_mode}", flush=True)
    ThreadingHTTPServer((a.host, a.port), make_handler(svc)).serve_forever()


if __name__ == "__main__":
    main()
