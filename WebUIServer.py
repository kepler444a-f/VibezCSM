"""
WebUIServer.py — Modern Web UI alternative to BasicUIManager.py
Runs a local HTTP server on port 8080 and serves the web frontend.
Proxies AI requests to Ollama and reads/writes the same local_ai_memory.db.

Usage:
    python WebUIServer.py

Then open: http://localhost:8080
"""

import json
import sqlite3
import urllib.request
import urllib.error
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

# ── Config — all paths are relative to THIS script's directory ─────────────────
BASE_DIR = Path(__file__).resolve().parent
PORT     = 8080
OLLAMA_HOST = "http://127.0.0.1:11434"
DB_PATH  = BASE_DIR / "local_ai_memory.db"
WEB_DIR  = BASE_DIR / "web_ui"


# ── Database helpers (mirrors DataBaseManager.py) ──────────────────────────────

def db_init():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                date_submitted TEXT,
                urgency_intent TEXT,
                motivation_score TEXT,
                timeline TEXT,
                location TEXT,
                contact_number TEXT,
                raw_message TEXT
            )
        """)
        conn.commit()


def db_save(name, date, urgency_intent, motivation, timeline, location, contact, raw_message):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """INSERT INTO leads
               (name, date_submitted, urgency_intent, motivation_score,
                timeline, location, contact_number, raw_message)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, date, urgency_intent, motivation, timeline, location, contact, raw_message)
        )
        conn.commit()


def db_get_all():
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            """SELECT id, name, date_submitted, urgency_intent,
                      motivation_score, timeline, location, contact_number
               FROM leads ORDER BY id DESC"""
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


# ── Ollama helpers ─────────────────────────────────────────────────────────────

def ollama_get_models():
    try:
        req = urllib.request.Request(f"{OLLAMA_HOST}/api/tags")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
            return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


def ollama_process_lead(model, context, prompt):
    system_instructions = (
        "You are an expert real estate data extraction and lead qualification assistant. "
        "Evaluate the user's message and extract the requested details. "
        "CRITICAL: If a detail is missing, you MUST output 'Not provided'.\n\n"
        "SCORING RULES:\n"
        "- Motivation Score: Rate from '1/10' to '10/10'. 10/10 means immediate distress "
        "(foreclosure, desperate to sell). 1/10 means just browsing or asking a casual question. "
        "If there is no context to gauge motivation, output 'Not provided'."
    )

    json_schema = {
        "type": "object",
        "properties": {
            "Name":             {"type": "string", "description": "The sender's name."},
            "Urgency & Intent": {"type": "string", "description": "Summarize urgency and goal."},
            "Motivation Score": {"type": "string", "description": "Score 1/10 to 10/10."},
            "Timeline":         {"type": "string", "description": "When they need to move/close."},
            "Location":         {"type": "string", "description": "Property address, city, or state."},
            "Contact Number":   {"type": "string", "description": "Phone number."}
        },
        "required": ["Name", "Urgency & Intent", "Motivation Score", "Timeline", "Location", "Contact Number"]
    }

    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system_instructions},
            {"role": "user",   "content": f"Additional Context/Rules: {context}\n\nMessage to parse: {prompt}"}
        ],
        "stream": False,
        "format": json_schema
    }).encode()

    req = urllib.request.Request(
        f"{OLLAMA_HOST}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req) as resp:
        body = json.loads(resp.read())
        content = body.get("message", {}).get("content", "{}")
        return json.loads(content)


# ── HTTP Request Handler ───────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        print(f"  [{self.command}] {self.path}")

    # ── helpers ───────────────────────────────────────────────────────────────

    def _send_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, msg, status=500):
        self._send_json({"error": msg}, status)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length)) if length else {}

    def _serve_file(self, filepath: Path):
        if not filepath.exists() or not filepath.is_file():
            print(f"  404 — file not found: {filepath}")
            body = f"404 Not Found: {filepath.name}".encode()
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        suffix = filepath.suffix.lower()
        mime = {
            ".html": "text/html; charset=utf-8",
            ".css":  "text/css",
            ".js":   "application/javascript",
            ".ico":  "image/x-icon",
            ".png":  "image/png",
            ".svg":  "image/svg+xml",
        }.get(suffix, "application/octet-stream")

        body = filepath.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ── routing ───────────────────────────────────────────────────────────────

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        url_path = self.path.split("?")[0]

        # ── API routes ────────────────────────────────────────────────────────
        if url_path == "/api/models":
            models = ollama_get_models()
            if models:
                self._send_json({"models": models})
            else:
                self._send_error_json(
                    "Could not reach Ollama. Make sure it is running ('ollama serve') and try again.",
                    503
                )
            return

        if url_path == "/api/leads":
            self._send_json({"leads": db_get_all()})
            return

        # ── Static file routes ────────────────────────────────────────────────
        if url_path in ("/", "/index.html"):
            self._serve_file(WEB_DIR / "index.html")
            return

        # Any other path: try to serve from web_ui/
        # Strip leading slash and prevent path traversal
        rel = url_path.lstrip("/")
        target = (WEB_DIR / rel).resolve()
        if WEB_DIR.resolve() in target.parents or target == WEB_DIR.resolve():
            self._serve_file(target)
        else:
            self._send_error_json("Forbidden", 403)

    def do_POST(self):
        if self.path != "/api/process":
            self._send_error_json("Not found", 404)
            return

        body = self._read_body()
        model   = body.get("model", "").strip()
        context = body.get("context", "").strip()
        prompt  = body.get("prompt", "").strip()

        if not prompt:
            self._send_error_json("Prompt cannot be empty.", 400)
            return
        if not model:
            self._send_error_json("No model selected.", 400)
            return

        try:
            data = ollama_process_lead(model, context, prompt)

            name           = data.get("Name", "Not provided")
            urgency_intent = data.get("Urgency & Intent", "Not provided")
            motivation     = data.get("Motivation Score", "Not provided")
            timeline       = data.get("Timeline", "Not provided")
            location       = data.get("Location", "Not provided")
            contact        = data.get("Contact Number", "Not provided")
            date_submitted = datetime.now().strftime("%Y-%m-%d %H:%M")

            db_save(name, date_submitted, urgency_intent, motivation,
                    timeline, location, contact, prompt)

            self._send_json({
                "ok": True,
                "lead": {
                    "name": name,
                    "date_submitted": date_submitted,
                    "urgency_intent": urgency_intent,
                    "motivation_score": motivation,
                    "timeline": timeline,
                    "location": location,
                    "contact_number": contact
                }
            })

        except urllib.error.URLError as e:
            self._send_error_json(
                f"Could not connect to Ollama at {OLLAMA_HOST}. "
                f"Make sure 'ollama serve' is running. Detail: {e}"
            )
        except json.JSONDecodeError as e:
            self._send_error_json(f"AI returned invalid JSON: {e}")
        except Exception as e:
            self._send_error_json(f"Unexpected error: {e}")


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    # Tell the user exactly what paths are being used
    print("=" * 60)
    print("  VibezCSM — Web UI Server")
    print("=" * 60)
    print(f"  Script dir  : {BASE_DIR}")
    print(f"  web_ui dir  : {WEB_DIR}")
    print(f"  index.html  : {WEB_DIR / 'index.html'}  exists={( WEB_DIR / 'index.html').exists()}")
    print(f"  Database    : {DB_PATH}")
    print(f"  Ollama      : {OLLAMA_HOST}")
    print(f"  Port        : {PORT}")
    print("=" * 60)

    if not WEB_DIR.exists():
        print(f"\n  ERROR: web_ui folder not found at:\n  {WEB_DIR}")
        print("  Make sure the 'web_ui' folder (with index.html inside) is")
        print("  in the same directory as WebUIServer.py.\n")
        return

    if not (WEB_DIR / "index.html").exists():
        print(f"\n  ERROR: index.html not found inside:\n  {WEB_DIR}\n")
        return

    db_init()

    server = HTTPServer(("127.0.0.1", PORT), Handler)
    print(f"\n  Open in browser:  http://localhost:{PORT}")
    print("  Press Ctrl+C to stop.\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Server stopped.")


if __name__ == "__main__":
    main()