"""Battery Guardian — HTTP request handler."""

import http.server
import json
import os
import secrets
import threading

from bg_config import VERSION
from bg_state import state, state_lock, stop_scan
from bg_history import HistoryManager
from bg_platform import get_mac_model
from bg_scanner import perform_scan
from bg_automation import generate_share_report, install_launch_agent

import sys

if getattr(sys, 'frozen', False):
    _HERE = sys._MEIPASS
else:
    _HERE = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(_HERE, "bg_template.html"), "r") as _f:
    _raw_template = _f.read()
HTML_TEMPLATE = _raw_template.replace("{{VERSION}}", VERSION)

with open(os.path.join(_HERE, "bg_guide.html"), "r") as _f:
    _raw_guide = _f.read()
HTML_GUIDE = _raw_guide.replace("{{VERSION}}", VERSION)


class AppHandler(http.server.SimpleHTTPRequestHandler):
    api_token = secrets.token_urlsafe(32)
    allowed_origins = set()

    @classmethod
    def configure(cls, api_token, port):
        cls.api_token = api_token
        cls.allowed_origins = {
            f"http://127.0.0.1:{port}",
            f"http://localhost:{port}",
        }

    def log_message(self, format, *args):
        pass

    def _send_json(self, value, status=200):
        payload = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(payload)

    def _authorized_api_request(self):
        supplied = self.headers.get("X-Battery-Guardian-Token", "")
        if not secrets.compare_digest(supplied, self.api_token):
            self._send_json({"error": "forbidden"}, status=403)
            return False

        origin = self.headers.get("Origin")
        if origin and origin not in self.allowed_origins:
            self._send_json({"error": "forbidden origin"}, status=403)
            return False
        return True

    def _send_html(self, template):
        payload = template.replace("{{API_TOKEN}}", self.api_token).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send_html(HTML_TEMPLATE)
        elif self.path == "/guide.html":
            self._send_html(HTML_GUIDE)
        elif self.path == "/api/status":
            if not self._authorized_api_request(): return
            with state_lock:
                self._send_json(state)
        elif self.path == "/api/history":
            if not self._authorized_api_request(): return
            self._send_json(HistoryManager.load())
        elif self.path == "/api/info":
            if not self._authorized_api_request(): return
            last = HistoryManager.get_last_scan()
            sn = last["parsed"].get("Serial", "--") if last and "parsed" in last else "--"
            info = {"model": get_mac_model(), "version": VERSION, "serial": sn}
            self._send_json(info)
        else:
            self.send_error(404)

    def do_POST(self):
        if not self._authorized_api_request():
            return
        if self.path == "/api/scan":
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len) if content_len else b"{}"
            try:
                params = json.loads(body) if body else {}
            except Exception:
                params = {}
            mode = params.get("mode", "full")
            threading.Thread(target=perform_scan, args=(mode,), daemon=True).start()
            self._send_json({"started": True})
        elif self.path == "/api/cancel":
            stop_scan.set()
            self._send_json({"cancelled": True})
        elif self.path == "/api/export":
            success, msg = HistoryManager.export_to_desktop()
            self._send_json({"success": success, "msg": msg})
        elif self.path == "/api/automate":
            content_len = int(self.headers.get("Content-Length", 0))
            try:
                body = json.loads(self.rfile.read(content_len))
            except Exception:
                body = {}
            days = max(1, min(365, int(body.get("days", 7))))
            hour = max(0, min(23, int(body.get("hour", 20))))
            minute = max(0, min(59, int(body.get("minute", 0))))
            success, msg = install_launch_agent(days, hour, minute)
            self._send_json({"success": success, "msg": msg})
        elif self.path == "/api/share":
            with state_lock:
                report = generate_share_report()
            self._send_json({"report": report})
        else:
            self.send_error(404)
