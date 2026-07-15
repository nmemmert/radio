#!/usr/bin/env python3
import base64
import json
import os
import socket
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ADMIN_USER     = os.environ.get("ICECAST_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("ICECAST_ADMIN_PASSWORD", "changeme-admin")
CONFIG_DIR     = Path("/config")
SETTINGS_ENV   = CONFIG_DIR / "settings.env"
HISTORY_LOG    = CONFIG_DIR / "history.log"
HERE           = Path(__file__).parent

DEFAULTS = {
    "STATION_NAME":        "My Radio",
    "STATION_DESCRIPTION": "Personal music stream",
    "GENRE":               "Various",
    "CROSSFADE_DURATION":  "3",
    "PODCAST_FEED_URL":    "",
    "PODCAST_TIME":        "",
}

def read_settings():
    s = dict(DEFAULTS)
    if SETTINGS_ENV.exists():
        for line in SETTINGS_ENV.read_text().splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                s[k.strip()] = v.strip().strip('"')
    return s

def write_settings(data):
    CONFIG_DIR.mkdir(exist_ok=True)
    lines = [f'{k}="{str(data.get(k, DEFAULTS.get(k, ""))).replace(chr(34), chr(92)+chr(34))}"'
             for k in DEFAULTS]
    SETTINGS_ENV.write_text("\n".join(lines) + "\n")

def read_history(n=25):
    if not HISTORY_LOG.exists():
        return []
    lines = HISTORY_LOG.read_text().splitlines()
    out = []
    for line in reversed(lines[-n:]):
        parts = line.split(" | ", 2)
        if len(parts) == 3:
            out.append({"ts": parts[0], "artist": parts[1], "title": parts[2]})
    return out

def liquidsoap_cmd(cmd):
    try:
        with socket.create_connection(("127.0.0.1", 1234), timeout=3) as s:
            s.sendall((cmd + "\nquit\n").encode())
            return s.recv(1024).decode(errors="replace").strip()
    except Exception as e:
        return f"error: {e}"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def _auth_ok(self):
        hdr = self.headers.get("Authorization", "")
        if not hdr.startswith("Basic "):
            return False
        try:
            user, _, pw = base64.b64decode(hdr[6:]).decode().partition(":")
            return user == ADMIN_USER and pw == ADMIN_PASSWORD
        except Exception:
            return False

    def _challenge(self):
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Radio Admin"')
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, body):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self._auth_ok():
            self._challenge(); return

        p = self.path.split("?")[0]

        if p in ("/panel", "/panel/", "/panel/index.html"):
            self._html((HERE / "index.html").read_bytes())
        elif p == "/panel/api/settings":
            self._json(read_settings())
        elif p == "/panel/api/history":
            self._json(read_history())
        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        if not self._auth_ok():
            self._challenge(); return

        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length)
        p      = self.path.split("?")[0]

        if p == "/panel/api/settings":
            try:
                data = json.loads(body)
                filtered = {k: data.get(k, DEFAULTS[k]) for k in DEFAULTS}
                write_settings(filtered)
                self._json({"ok": True})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 400)

        elif p == "/panel/api/skip":
            result = liquidsoap_cmd("music.skip")
            self._json({"ok": "error" not in result, "result": result})

        else:
            self.send_response(404); self.end_headers()


if __name__ == "__main__":
    CONFIG_DIR.mkdir(exist_ok=True)
    print("Radio admin panel → http://0.0.0.0:8080/panel/", flush=True)
    HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
