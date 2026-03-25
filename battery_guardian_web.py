#!/usr/bin/env python3
"""
Mac Battery Guardian v1.1
A native macOS battery forensics tool.
"""

import json
import logging
import os
import socketserver
import subprocess
import sys
import threading
import webbrowser

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("battery_guardian")

from bg_config import PORT
from bg_platform import check_platform, get_mac_model
from bg_state import state
from bg_scanner import perform_scan
from bg_automation import install_launch_agent
from bg_server import AppHandler


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Mac Battery Guardian")
    parser.add_argument("--auto", action="store_true", help="Run headless (no GUI, just log)")
    parser.add_argument("--enable-automation", type=int, metavar="DAYS", help="Enable daily scans for N days")
    parser.add_argument("--no-window", action="store_true", help="Use browser instead of native window")
    args = parser.parse_args()

    # Automation CLI
    if args.enable_automation:
        success, msg = install_launch_agent(args.enable_automation)
        if success:
            logger.info(msg)
            sys.exit(0)
        else:
            logger.error(msg)
            sys.exit(1)

    # Headless mode
    if args.auto:
        try:
            config_path = os.path.expanduser("~/.battery_guardian/automation_config.json")
            if os.path.exists(config_path):
                with open(config_path) as f:
                    config = json.load(f)
                from datetime import datetime
                installed_at = datetime.fromisoformat(config["installed_at"])
                expires_days = config.get("expires_after_days", 0)
                if expires_days > 0 and (datetime.now() - installed_at).days >= expires_days:
                    plist_path = os.path.expanduser(
                        "~/Library/LaunchAgents/com.batteryguardian.daily.plist"
                    )
                    subprocess.run(["launchctl", "unload", plist_path], capture_output=True)
                    if os.path.exists(plist_path):
                        os.remove(plist_path)
                    logger.info("Automation expired. LaunchAgent unloaded cleanly.")
                    sys.exit(0)
        except Exception as e:
            logger.warning(f"Failed to check automation expiry: {e}")

        ok, err = check_platform()
        if not ok:
            logger.error(f"Platform error: {err}")
            sys.exit(1)
        logger.info("Running Headless Scan...")
        perform_scan()
        logger.info(f"Verdict: {state['verdict']} | Health: {state['health_score']}/100")
        sys.exit(0)

    # GUI mode
    ok, platform_err = check_platform()
    mac_model = get_mac_model() if ok else "Unknown"
    state["mac_model"] = mac_model

    # Find an open port
    port_found = False
    active_port = PORT
    for p in range(PORT, PORT + 10):
        try:
            httpd = socketserver.ThreadingTCPServer(("127.0.0.1", p), AppHandler)
            active_port = p
            port_found = True
            break
        except OSError:
            continue

    if not port_found:
        logger.error(f"No open port found ({PORT}-{PORT + 9})")
        sys.exit(1)

    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()
    logger.info(f"Server running at http://localhost:{active_port}")

    use_native = not args.no_window
    if use_native:
        try:
            import webview
            webview.create_window(
                "Battery Guardian",
                f"http://localhost:{active_port}",
                width=800,
                height=920,
                resizable=True,
                min_size=(600, 700),
            )
            webview.start()
        except ImportError:
            logger.warning("pywebview not installed. Falling back to browser.")
            webbrowser.open(f"http://localhost:{active_port}")
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                pass
    else:
        webbrowser.open(f"http://localhost:{active_port}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
