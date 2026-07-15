#!/usr/bin/env python3
import base64
import json
import os
import re
import socket
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
        if not self._auth_ok():
            self._challenge(); return
        p = self._path()
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
