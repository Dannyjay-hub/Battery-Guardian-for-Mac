"""Battery Guardian — HTTP request handler."""

import http.server
import json
import os
import threading

from bg_config import VERSION
from bg_state import state, state_lock, stop_scan
from bg_history import HistoryManager
from bg_platform import get_mac_model
from bg_scanner import perform_scan
from bg_automation import generate_share_report, install_launch_agent

_HERE = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(_HERE, "bg_template.html"), "r") as _f:
    _raw_template = _f.read()
HTML_TEMPLATE = _raw_template.replace("{{VERSION}}", VERSION)

with open(os.path.join(_HERE, "bg_guide.html"), "r") as _f:
    _raw_guide = _f.read()
HTML_GUIDE = _raw_guide.replace("{{VERSION}}", VERSION)


class AppHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode())
        elif self.path == "/api/status":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            with state_lock:
                self.wfile.write(json.dumps(state).encode())
        elif self.path == "/api/history":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(HistoryManager.load()).encode())
        elif self.path == "/api/info":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            last = HistoryManager.get_last_scan()
            sn = last["parsed"].get("Serial", "--") if last and "parsed" in last else "--"
            info = {"model": get_mac_model(), "version": VERSION, "serial": sn}
            self.wfile.write(json.dumps(info).encode())
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == "/api/scan":
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len) if content_len else b"{}"
            try:
                params = json.loads(body) if body else {}
            except Exception:
                params = {}
            mode = params.get("mode", "full")
            threading.Thread(target=perform_scan, args=(mode,), daemon=True).start()
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"started": True}).encode())
        elif self.path == "/api/cancel":
            stop_scan.set()
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"cancelled": True}).encode())
        elif self.path == "/api/export":
            success, msg = HistoryManager.export_to_desktop()
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": success, "msg": msg}).encode())
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
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": success, "msg": msg}).encode())
        elif self.path == "/api/share":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            with state_lock:
                report = generate_share_report()
            self.wfile.write(json.dumps({"report": report}).encode())
        else:
            self.send_error(404)
