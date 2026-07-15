#!/usr/bin/env python3
import base64
import http.client
import json
import os
import re
import socket
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ADMIN_USER     = os.environ.get("ICECAST_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("ICECAST_ADMIN_PASSWORD", "changeme-admin")
CONFIG_DIR     = Path("/config")
SETTINGS_ENV   = CONFIG_DIR / "settings.env"
HISTORY_LOG    = CONFIG_DIR / "history.log"
PLAYLISTS_DIR  = CONFIG_DIR / "playlists"
SCHEDULE_FILE  = CONFIG_DIR / "schedule.json"
MUSIC_DIR      = Path("/music")
HERE           = Path(__file__).parent

AUDIO_EXTS = {'.mp3', '.flac', '.ogg', '.aac', '.m4a', '.wav', '.opus', '.ape', '.wma'}

SETTING_KEYS = ["STATION_NAME", "STATION_DESCRIPTION", "GENRE",
                "CROSSFADE_DURATION", "PODCAST_FEED_URL", "PODCAST_TIME"]
DEFAULTS = {
    "STATION_NAME":        "My Radio",
    "STATION_DESCRIPTION": "Personal music stream",
    "GENRE":               "Various",
    "CROSSFADE_DURATION":  "3",
    "PODCAST_FEED_URL":    "",
    "PODCAST_TIME":        "",
}

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

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
    lines = []
    for k in SETTING_KEYS:
        v = str(data.get(k, DEFAULTS.get(k, ""))).replace('"', '\\"')
        lines.append(f'{k}="{v}"')
    SETTINGS_ENV.write_text("\n".join(lines) + "\n")

# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Library
# ---------------------------------------------------------------------------

def scan_library():
    if not MUSIC_DIR.exists():
        return []
    entries = []
    for p in sorted(MUSIC_DIR.rglob("*")):
        if p.is_file() and p.suffix.lower() in AUDIO_EXTS:
            rel = str(p.relative_to(MUSIC_DIR))
            entries.append({"path": str(p), "display": rel})
    return entries

# ---------------------------------------------------------------------------
# Playlists
# ---------------------------------------------------------------------------

def _safe_name(name):
    return re.sub(r"[^a-zA-Z0-9_\-]", "", name)

def list_playlists():
    PLAYLISTS_DIR.mkdir(parents=True, exist_ok=True)
    return [f.stem for f in sorted(PLAYLISTS_DIR.glob("*.m3u"))]

def read_playlist(name):
    f = PLAYLISTS_DIR / f"{_safe_name(name)}.m3u"
    if not f.exists():
        return []
    return [l.strip() for l in f.read_text().splitlines()
            if l.strip() and not l.startswith("#")]

def write_playlist(name, paths):
    PLAYLISTS_DIR.mkdir(parents=True, exist_ok=True)
    name = _safe_name(name)
    if not name:
        raise ValueError("invalid playlist name")
    content = "#EXTM3U\n" + "\n".join(paths) + "\n"
    (PLAYLISTS_DIR / f"{name}.m3u").write_text(content)
    return name

def delete_playlist(name):
    name = _safe_name(name)
    f = PLAYLISTS_DIR / f"{name}.m3u"
    if f.exists():
        f.unlink()
    # Remove from schedule too
    entries = read_schedule()
    entries = [e for e in entries if e.get("name") != name]
    write_schedule(entries)

# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------

def read_schedule():
    if not SCHEDULE_FILE.exists():
        return []
    try:
        return json.loads(SCHEDULE_FILE.read_text())
    except Exception:
        return []

def write_schedule(entries):
    CONFIG_DIR.mkdir(exist_ok=True)
    SCHEDULE_FILE.write_text(json.dumps(entries, indent=2))

def upsert_schedule(name, time_str):
    name = _safe_name(name)
    entries = read_schedule()
    file_path = str(PLAYLISTS_DIR / f"{name}.m3u")
    existing = next((e for e in entries if e["name"] == name), None)
    if time_str:
        if existing:
            existing["time"] = time_str
            existing["file"] = file_path
        else:
            entries.append({"name": name, "file": file_path, "time": time_str})
    else:
        entries = [e for e in entries if e["name"] != name]
    write_schedule(entries)

# ---------------------------------------------------------------------------
# Liquidsoap skip
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Icecast proxy — admin shares icecast's network namespace so localhost:8000
# is always Icecast, regardless of what external port the host exposes.
# ---------------------------------------------------------------------------

ICECAST_ORIGIN = "http://127.0.0.1:8000"

# Paths that should be transparently proxied to Icecast.
PROXY_PREFIXES = ("/stream", "/status-json.xsl", "/status.xsl", "/admin/")

def _proxy(handler, path):
    url = ICECAST_ORIGIN + path
    try:
        req = urllib.request.Request(url)
        # Forward basic auth header if present (needed for /admin/ endpoints)
        auth_hdr = handler.headers.get("Authorization")
        if auth_hdr:
            req.add_header("Authorization", auth_hdr)
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read()
            handler.send_response(resp.status)
            for k, v in resp.headers.items():
                if k.lower() in ("content-type", "content-length", "cache-control",
                                  "icy-metaint", "icy-name", "icy-description",
                                  "icy-genre", "icy-br", "icy-pub"):
                    handler.send_header(k, v)
            handler.send_header("Access-Control-Allow-Origin", "*")
            handler.end_headers()
            handler.wfile.write(body)
    except Exception as e:
        handler.send_response(502)
        handler.end_headers()
        handler.wfile.write(str(e).encode())

def _proxy_stream(handler, path):
    """Streaming proxy for /stream — pipes bytes as they arrive."""
    url = ICECAST_ORIGIN + path
    try:
        with urllib.request.urlopen(url, timeout=None) as resp:
            handler.send_response(200)
            for k, v in resp.headers.items():
                if k.lower() in ("content-type", "transfer-encoding",
                                  "icy-metaint", "icy-name", "icy-description",
                                  "icy-genre", "icy-br", "icy-pub"):
                    handler.send_header(k, v)
            handler.send_header("Cache-Control", "no-cache")
            handler.end_headers()
            while True:
                chunk = resp.read(4096)
                if not chunk:
                    break
                handler.wfile.write(chunk)
                handler.wfile.flush()
    except (BrokenPipeError, ConnectionResetError):
        pass  # client disconnected
    except Exception:
        pass

DOCKER_SOCK     = "/var/run/docker.sock"
LIQUIDSOAP_NAME = os.environ.get("LIQUIDSOAP_CONTAINER", "liquidsoap")

class _UnixConn(http.client.HTTPConnection):
    def __init__(self, sock_path):
        super().__init__("localhost")
        self._sock_path = sock_path
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(self._sock_path)

def restart_liquidsoap():
    try:
        conn = _UnixConn(DOCKER_SOCK)
        conn.request("POST", f"/containers/{LIQUIDSOAP_NAME}/restart?t=3")
        resp = conn.getresponse()
        resp.read()
        return resp.status in (204, 200)
    except Exception as e:
        return False, str(e)

def liquidsoap_cmd(cmd):
    try:
        with socket.create_connection(("127.0.0.1", 1234), timeout=3) as s:
            s.sendall((cmd + "\nquit\n").encode())
            return s.recv(1024).decode(errors="replace").strip()
    except Exception as e:
        return f"error: {e}"

# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

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

    def _path(self):
        return self.path.split("?")[0]

    def do_GET(self):
        p = self._path()

        # Proxy Icecast endpoints transparently
        if any(p == pfx or p.startswith(pfx) for pfx in PROXY_PREFIXES):
            if p.startswith("/stream"):
                _proxy_stream(self, self.path)  # include query string for cache-busting
            else:
                _proxy(self, p)
            return

        # Public routes — no auth required
        if p in ("/", "/index.html"):
            self._html((HERE / "public.html").read_bytes()); return
        if p in ("/embed", "/embed.html"):
            self._html((HERE / "embed.html").read_bytes()); return
        if p == "/api/public/history":
            self._json(read_history()); return
        if p == "/api/public/schedule":
            self._json(read_schedule()); return

        # Admin routes — auth required
        if not self._auth_ok():
            self._challenge(); return
        if p in ("/panel", "/panel/", "/panel/index.html"):
            self._html((HERE / "index.html").read_bytes())
        elif p == "/panel/api/settings":
            self._json(read_settings())
        elif p == "/panel/api/history":
            self._json(read_history())
        elif p == "/panel/api/library":
            self._json(scan_library())
        elif p == "/panel/api/playlists":
            self._json(list_playlists())
        elif p.startswith("/panel/api/playlists/"):
            name = p.removeprefix("/panel/api/playlists/")
            self._json(read_playlist(name))
        elif p == "/panel/api/schedule":
            self._json(read_schedule())
        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        if not self._auth_ok():
            self._challenge(); return
        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length)
        p      = self._path()

        if p == "/panel/api/settings":
            try:
                data     = json.loads(body)
                filtered = {k: data.get(k, DEFAULTS[k]) for k in SETTING_KEYS}
                write_settings(filtered)
                self._json({"ok": True})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 400)

        elif p == "/panel/api/skip":
            result = liquidsoap_cmd("music.skip")
            self._json({"ok": "error" not in result, "result": result})

        elif p.startswith("/panel/api/playlists/"):
            name = p.removeprefix("/panel/api/playlists/")
            try:
                data      = json.loads(body)
                tracks    = data.get("tracks", [])
                time_str  = data.get("time", "").strip()
                saved     = write_playlist(name, tracks)
                upsert_schedule(saved, time_str)
                self._json({"ok": True, "name": saved})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 400)

        elif p == "/panel/api/schedule":
            try:
                entries = json.loads(body)
                write_schedule(entries)
                self._json({"ok": True})
            except Exception as e:
                self._json({"ok": False, "error": str(e)}, 400)

        elif p == "/panel/api/restart":
            ok = restart_liquidsoap()
            self._json({"ok": ok})

        else:
            self.send_response(404); self.end_headers()

    def do_DELETE(self):
        if not self._auth_ok():
            self._challenge(); return
        p = self._path()
        if p.startswith("/panel/api/playlists/"):
            name = p.removeprefix("/panel/api/playlists/")
            delete_playlist(name)
            self._json({"ok": True})
        else:
            self.send_response(404); self.end_headers()


if __name__ == "__main__":
    CONFIG_DIR.mkdir(exist_ok=True)
    print("Radio admin panel → http://0.0.0.0:8080/panel/", flush=True)
    HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
