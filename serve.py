#!/usr/bin/env python3
"""
Outlier Lab — local admin dashboard.

Run this and a browser tab will open at http://localhost:4747/admin
where you can:
  • paste/save your Apify API token
  • search for Instagram creators live (typeahead via Apify)
  • see each result's profile pic, follower count, verified badge
  • one-click add / remove from your tracking list
  • trigger a fresh refresh on demand (also runs every Sunday via GH Actions)

Pure stdlib — no pip install needed. Localhost-only binding.
"""

import io
import json
import os
import re
import socketserver
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"
CONFIG_FILE = ROOT / "config.json"
ADMIN_HTML = ROOT / "admin.html"

PORT = 4747
HOST = "127.0.0.1"

# Apify actor IDs
IG_SCRAPER = "shu8hvrXbJbY3Eb9W"  # apify/instagram-scraper (general)


# ───────────────────────── helpers ─────────────────────────

def load_env_token():
    if not ENV_FILE.exists():
        return ""
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line.startswith("APIFY_TOKEN="):
            return line.split("=", 1)[1].strip()
    return ""


def save_env_token(token):
    body = (
        "# Apify API token — used by refresh.py + serve.py.\n"
        "# Set this as the APIFY_TOKEN GitHub Actions secret for the Sunday cron.\n"
        f"APIFY_TOKEN={token}\n"
    )
    ENV_FILE.write_text(body)


def load_config():
    if not CONFIG_FILE.exists():
        return {"creators": []}
    try:
        return json.loads(CONFIG_FILE.read_text())
    except json.JSONDecodeError:
        return {"creators": []}


def save_config(config):
    CONFIG_FILE.write_text(json.dumps(config, indent=2) + "\n")


def apify_run_sync(actor_id, input_body, token, timeout=90):
    """Call Apify's run-sync-get-dataset-items endpoint. Returns list of items."""
    url = f"https://api.apify.com/v2/acts/{actor_id}/run-sync-get-dataset-items?token={token}"
    req = urllib.request.Request(
        url,
        data=json.dumps(input_body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def normalize_profile(item):
    """Reduce a scraped profile/search-result to the shape we store."""
    return {
        "handle": item.get("username", ""),
        "name": item.get("fullName") or item.get("full_name") or "",
        "followers": item.get("followersCount") or item.get("edge_followed_by", {}).get("count") or 0,
        "posts": item.get("postsCount") or 0,
        "verified": bool(item.get("verified") or item.get("is_verified")),
        "private": bool(item.get("private") or item.get("is_private")),
        "profilePic": item.get("profilePicUrlHD") or item.get("profilePicUrl") or item.get("profile_pic_url") or "",
    }


# ───────────────────────── HTTP handler ─────────────────────────

class AdminHandler(BaseHTTPRequestHandler):

    # ---- request helpers ----

    def _json(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _html(self, status, body, content_type="text/html; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

    def log_message(self, fmt, *args):
        # Quieter logging — only show our own prints
        return

    # ---- routes ----

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path in ("/", "/admin", "/admin/"):
            if not ADMIN_HTML.exists():
                self._html(500, "admin.html missing")
                return
            self._html(200, ADMIN_HTML.read_bytes())
            return

        if path == "/api/state":
            token = load_env_token()
            config = load_config()
            self._json(200, {
                "tokenSet": bool(token and token.startswith("apify_api_")),
                "tokenPrefix": token[:16] + "…" if token else "",
                "creators": config.get("creators", []),
            })
            return

        if path == "/api/schedule":
            wf_path = ROOT / ".github" / "workflows" / "refresh.yml"
            if not wf_path.exists():
                self._json(200, {"cron": None})
                return
            content = wf_path.read_text()
            # commented out → off
            if re.search(r"^\s*#\s*schedule:", content, re.MULTILINE):
                self._json(200, {"cron": "off"})
                return
            m = re.search(r'-\s*cron:\s*"([^"]+)"', content)
            self._json(200, {"cron": m.group(1) if m else None})
            return

        if path == "/api/search":
            q = (query.get("q", [""])[0] or "").strip()
            if not q or len(q) < 2:
                self._json(200, {"results": []})
                return
            token = load_env_token()
            if not token:
                self._json(400, {"error": "no_token", "message": "Save your Apify token first."})
                return
            try:
                items = apify_run_sync(IG_SCRAPER, {
                    "search": q,
                    "searchType": "user",
                    "searchLimit": 8,
                    "resultsType": "details",
                    "resultsLimit": 1,
                }, token, timeout=45)
            except urllib.error.HTTPError as e:
                self._json(502, {"error": "apify", "message": f"Apify HTTP {e.code}"})
                return
            except Exception as e:
                self._json(502, {"error": "apify", "message": str(e)[:140]})
                return
            results = []
            for it in items:
                if not it.get("username") or it.get("error"):
                    continue
                results.append(normalize_profile(it))
            self._json(200, {"results": results})
            return

        # serve any other static file in the project root (so admin.html can <link> styles/images if added later)
        safe_path = ROOT / path.lstrip("/")
        try:
            safe_path = safe_path.resolve()
            safe_path.relative_to(ROOT)
        except (ValueError, OSError):
            self._json(404, {"error": "not_found"})
            return
        if safe_path.is_file():
            ext = safe_path.suffix.lower()
            ct = {
                ".html": "text/html; charset=utf-8",
                ".css": "text/css",
                ".js": "application/javascript",
                ".json": "application/json",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".mp4": "video/mp4",
                ".svg": "image/svg+xml",
            }.get(ext, "application/octet-stream")
            self._html(200, safe_path.read_bytes(), content_type=ct)
            return

        self._json(404, {"error": "not_found"})

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/token":
            data = self._body()
            token = (data.get("token") or "").strip()
            if not token.startswith("apify_api_"):
                self._json(400, {"error": "invalid_token", "message": "Token should start with apify_api_"})
                return
            save_env_token(token)
            self._json(200, {"ok": True})
            return

        if path == "/api/lookup":
            data = self._body()
            handle = (data.get("handle") or "").lstrip("@").strip()
            if not handle:
                self._json(400, {"error": "no_handle"})
                return
            token = load_env_token()
            if not token:
                self._json(400, {"error": "no_token"})
                return
            try:
                items = apify_run_sync(IG_SCRAPER, {
                    "directUrls": [f"https://www.instagram.com/{handle}/"],
                    "resultsType": "details",
                    "resultsLimit": 1,
                }, token, timeout=45)
            except Exception as e:
                self._json(502, {"error": "apify", "message": str(e)[:140]})
                return
            if not items or items[0].get("error") or not items[0].get("username"):
                self._json(404, {"error": "not_found", "message": "Profile not found or empty."})
                return
            self._json(200, {"profile": normalize_profile(items[0])})
            return

        if path == "/api/creators":
            data = self._body()
            profile = data.get("profile")
            if not profile or not profile.get("handle"):
                self._json(400, {"error": "no_profile"})
                return
            config = load_config()
            creators = config.get("creators", [])
            if any(c["handle"] == profile["handle"] for c in creators):
                self._json(409, {"error": "already_added"})
                return
            creators.append(profile)
            config["creators"] = creators
            save_config(config)
            self._json(200, {"creators": creators})
            return

        if path == "/api/schedule":
            data = self._body()
            cron = (data.get("cron") or "").strip()
            wf_path = ROOT / ".github" / "workflows" / "refresh.yml"
            if not wf_path.exists():
                self._json(404, {"error": "workflow_missing"})
                return
            content = wf_path.read_text()

            if cron == "off":
                # Comment out the schedule block
                new_content = re.sub(
                    r"^(\s*)schedule:\s*\n(\s*-\s*cron:.*\n)",
                    lambda m: m.group(1) + "# schedule:\n" + re.sub(r"^", "# ", m.group(2)),
                    content,
                    count=1,
                    flags=re.MULTILINE,
                )
                if new_content == content:
                    # Maybe already off — try uncomment-target pattern
                    new_content = content
                wf_path.write_text(new_content)
                self._json(200, {"ok": True, "message": "Schedule disabled (cron commented out)."})
                return

            # Re-enable schedule if currently commented, and set the new cron
            if "# schedule:" in content:
                content = content.replace("# schedule:", "schedule:")
                content = re.sub(r"^# (\s*-\s*cron:.*)$", r"\1", content, flags=re.MULTILINE)
            new_content = re.sub(
                r'(-\s*cron:\s*")[^"]+(")',
                lambda m: m.group(1) + cron + m.group(2),
                content,
                count=1,
            )
            if new_content == content:
                # No match — workflow file shape changed
                self._json(500, {"error": "cant_patch", "message": "Couldn't find cron line in refresh.yml."})
                return
            wf_path.write_text(new_content)
            self._json(200, {"ok": True, "message": f"Schedule set to: {cron}. Commit & push to apply."})
            return

        if path == "/api/refresh":
            token = load_env_token()
            if not token:
                self._json(400, {"error": "no_token"})
                return
            # Fire refresh.py in a subprocess (long-running)
            env = {**os.environ, "APIFY_TOKEN": token}
            log_path = ROOT / "refresh.log"
            log_path.write_text(f"# Refresh started at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            with open(log_path, "ab") as logf:
                p = subprocess.Popen(
                    [sys.executable, str(ROOT / "refresh.py")],
                    cwd=str(ROOT), env=env, stdout=logf, stderr=subprocess.STDOUT,
                )
            self._json(200, {"ok": True, "pid": p.pid, "logPath": str(log_path)})
            return

        self._json(404, {"error": "not_found"})

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        m = re.match(r"^/api/creators/(?P<handle>[^/]+)$", path)
        if m:
            handle = urllib.parse.unquote(m.group("handle"))
            config = load_config()
            before = len(config.get("creators", []))
            config["creators"] = [c for c in config.get("creators", []) if c["handle"] != handle]
            save_config(config)
            self._json(200, {"removed": before - len(config["creators"]), "creators": config["creators"]})
            return

        self._json(404, {"error": "not_found"})


# ───────────────────────── server ─────────────────────────

class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


def main():
    url = f"http://{HOST}:{PORT}/admin"
    print(f"\n  ╔══════════════════════════════════════════════════════╗")
    print(f"  ║                                                      ║")
    print(f"  ║   OUTLIER LAB — Admin dashboard                      ║")
    print(f"  ║                                                      ║")
    print(f"  ║   Open in your browser:                              ║")
    print(f"  ║   {url:<53} ║")
    print(f"  ║                                                      ║")
    print(f"  ║   Press Ctrl+C to stop the server.                   ║")
    print(f"  ║                                                      ║")
    print(f"  ╚══════════════════════════════════════════════════════╝\n")

    # Open browser tab after a tiny delay so the user sees the banner first
    def _open():
        time.sleep(0.6)
        webbrowser.open(url)
    threading.Thread(target=_open, daemon=True).start()

    with ReusableTCPServer((HOST, PORT), AdminHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n  Goodbye.")


if __name__ == "__main__":
    main()
