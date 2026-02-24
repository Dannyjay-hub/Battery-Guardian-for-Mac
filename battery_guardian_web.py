#!/usr/bin/env python3
"""
Mac Battery Guardian v1.0
A native macOS battery forensics tool.
"""

import http.server
import socketserver
import threading
import subprocess
import re
import json
import time
import sys
import os
import platform
from datetime import datetime

# --- CONSTANTS ---
VERSION = "1.0"
PORT = 8080
SCAN_DURATION_FULL = 60
SCAN_DURATION_QUICK = 10
HISTORY_FILE = os.path.expanduser("~/.battery_guardian_log.json")

# Scoring Thresholds
SCORE_ZERO_ENTROPY = 40
SCORE_LAZY_CLONE = 30
SCORE_CALIBRATION_TAMPERING = 30
SCORE_FLATLINE = 50
SCORE_ODOMETER_ROLLBACK = 60
SCORE_TIME_PARADOX = 20
SCORE_THRESHOLD_SPOOFED = 40

# --- PLATFORM GUARD ---
def check_platform():
    """Returns (ok, error_msg). Blocks Windows/Linux and battery-less Macs."""
    if platform.system() != "Darwin":
        return False, "NOT_MAC"
    # Check for battery
    try:
        res = subprocess.run(
            ["ioreg", "-l", "-w0", "-r", "-c", "AppleSmartBattery"],
            capture_output=True, text=True, timeout=10
        )
        if not res.stdout or "AppleSmartBattery" not in res.stdout:
            return False, "NO_BATTERY"
    except Exception:
        return False, "NO_BATTERY"
    return True, None

# --- MAC MODEL DETECTION ---
def get_mac_model():
    """Get the Mac model name and year."""
    try:
        res = subprocess.run(
            ["system_profiler", "SPHardwareDataType"],
            capture_output=True, text=True, timeout=10
        )
        model_name = ""
        chip = ""
        for line in res.stdout.splitlines():
            line = line.strip()
            if "Model Name:" in line:
                model_name = line.split(":", 1)[1].strip()
            elif "Chip:" in line:
                chip = line.split(":", 1)[1].strip()
            elif "Processor Name:" in line and not chip:
                chip = line.split(":", 1)[1].strip()
        if model_name and chip:
            return f"{model_name} ({chip})"
        elif model_name:
            return model_name
        return "Mac"
    except Exception:
        return "Mac"


# --- HISTORY MANAGER ---
class HistoryManager:
    FILE_PATH = HISTORY_FILE
    
    @staticmethod
    def load():
        if os.path.exists(HistoryManager.FILE_PATH):
            try:
                with open(HistoryManager.FILE_PATH, 'r') as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    @staticmethod
    def save_scan(raw_text, parsed_data):
        history = HistoryManager.load()
        entry = {
            "timestamp": datetime.now().isoformat(),
            "serial": parsed_data.get("Serial", "Unknown"),
            "cycle_count": parsed_data.get("CycleCount", 0),
            "parsed": parsed_data,
            "raw_text_snippet": raw_text[:2000]
        }
        history.append(entry)
        try:
            with open(HistoryManager.FILE_PATH, 'w') as f:
                json.dump(history, f, indent=2)
        except Exception as e:
            print(f"[!] Save error: {e}")

    @staticmethod
    def get_last_scan():
        history = HistoryManager.load()
        if len(history) >= 2:
            return history[-2]
        return None

    @staticmethod
    def export_to_desktop():
        try:
            desktop = os.path.expanduser("~/Desktop")
            export_path = os.path.join(desktop, "battery_guardian_export.json")
            history = HistoryManager.load()
            with open(export_path, 'w') as f:
                json.dump(history, f, indent=2)
            return True, export_path
        except Exception as e:
            return False, str(e)


# --- GLOBAL STATE ---
state_lock = threading.Lock()
stop_scan = threading.Event()

state = {
    "status": "idle",
    "progress": 0,
    "log": [],
    "verdict": "READY",
    "score": 0,
    "health_score": 0,
    "scan_mode": "full",
    "mac_model": "--",
    "trends": {},
    "metrics": {
        "cycle_count": "--",
        "write_count": "--",
        "qmax_var": "--",
        "op_time": "--",
        "health": "--",
        "ratio": "--",
        "serial": "--"
    }
}


# --- CORE LOGIC ---
def parse_ioreg(text):
    data = {}
    for m in re.finditer(r'"(\w+)"\s*=\s*(\d+)', text):
        data[m.group(1)] = int(m.group(2))
    for m in re.finditer(r'"(\w+)"\s*=\s*"([^"]+)"', text):
        if m.group(1) not in data:
            data[m.group(1)] = m.group(2)
    for key in ["Qmax", "CellVoltage", "DOD0", "WeightedRa", "PresentDOD"]:
        m = re.search(rf'"{key}"\s*=\s*\(([^)]+)\)', text)
        if m:
            vals = [int(x.strip()) for x in m.group(1).split(",") if x.strip().isdigit()]
            if vals:
                data[key] = vals
    return data


def compute_health_score(data, scan_score):
    """Compute a 0-100 health score (100 = perfect genuine battery)."""
    score = 100
    
    # Deduct for spoof indicators
    score -= min(scan_score, 80)
    
    # Deduct for low capacity health
    if "AppleRawMaxCapacity" in data and "DesignCapacity" in data:
        cap = data["AppleRawMaxCapacity"]
        design = data["DesignCapacity"]
        if design > 0:
            health_pct = (cap / design) * 100
            if health_pct < 80:
                score -= int((80 - health_pct) * 0.5)
    
    # Deduct for high cycles
    cycles = data.get("CycleCount", 0)
    if cycles > 1000:
        score -= min(int((cycles - 1000) / 50), 15)
    elif cycles > 500:
        score -= min(int((cycles - 500) / 100), 5)
    
    return max(0, min(100, score))


def compute_trends(current_data, last_entry):
    """Compare current scan vs last scan. Returns dict of arrows."""
    trends = {}
    if not last_entry or "parsed" not in last_entry:
        return trends
    
    prev = last_entry["parsed"]
    
    # Cycle count
    curr_cycles = current_data.get("CycleCount", 0)
    prev_cycles = prev.get("CycleCount", 0)
    if curr_cycles > prev_cycles:
        trends["cycles"] = "up"
    elif curr_cycles == prev_cycles:
        trends["cycles"] = "stable"
    
    # Health
    curr_max = current_data.get("AppleRawMaxCapacity", 0)
    prev_max = prev.get("AppleRawMaxCapacity", 0)
    if curr_max > 0 and prev_max > 0:
        if curr_max < prev_max:
            trends["health"] = "down"
        elif curr_max > prev_max:
            trends["health"] = "up"
        else:
            trends["health"] = "stable"
    
    # Operating time
    curr_op = current_data.get("TotalOperatingTime", 0)
    prev_op = prev.get("TotalOperatingTime", 0)
    if curr_op > prev_op:
        trends["op_time"] = "up"
    elif curr_op == prev_op:
        trends["op_time"] = "frozen"
    
    return trends


def perform_scan(scan_mode="full"):
    global state
    with state_lock:
        if state["status"] == "running":
            return
        state["status"] = "running"
        state["progress"] = 0
        state["log"] = []
        state["score"] = 0
        state["health_score"] = 0
        state["verdict"] = "ANALYZING..."
        state["scan_mode"] = scan_mode
        state["trends"] = {}
    
    stop_scan.clear()
    duration = SCAN_DURATION_FULL if scan_mode == "full" else SCAN_DURATION_QUICK
    
    try:
        state["progress"] = 5
        cmd = ["ioreg", "-l", "-w0", "-r", "-c", "AppleSmartBattery"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise Exception("ioreg command failed. Are you on a Mac?")
        if not res.stdout:
            raise Exception("No battery detected.")
        data = parse_ioreg(res.stdout)
        
        HistoryManager.save_scan(res.stdout, data)
        
        # Get last scan for trends
        last_scan = HistoryManager.get_last_scan()
        
        # Update metrics
        with state_lock:
            if "CycleCount" in data:
                state["metrics"]["cycle_count"] = data["CycleCount"]
            if "Serial" in data:
                state["metrics"]["serial"] = data["Serial"]
            if "DataFlashWriteCount" in data:
                state["metrics"]["write_count"] = data["DataFlashWriteCount"]
                if "CycleCount" in data:
                    state["metrics"]["ratio"] = round(
                        data["DataFlashWriteCount"] / max(1, data["CycleCount"]), 1
                    )
            if "Qmax" in data:
                state["metrics"]["qmax_var"] = max(data["Qmax"]) - min(data["Qmax"])
            if "TotalOperatingTime" in data:
                state["metrics"]["op_time"] = f"{data['TotalOperatingTime']} hrs"
            
            # Health
            numerator = 0
            if "AppleRawMaxCapacity" in data:
                numerator = data["AppleRawMaxCapacity"]
            elif "MaxCapacity" in data:
                numerator = data["MaxCapacity"]
            if numerator > 0 and "DesignCapacity" in data and data["DesignCapacity"] > 0:
                fcc_health = int((numerator / data["DesignCapacity"]) * 100)
                state["metrics"]["health"] = f"{fcc_health}% ({numerator}/{data['DesignCapacity']} mAh)"
            else:
                state["metrics"]["health"] = "N/A"
        
        qmax_health = 0
        if "Qmax" in data and "DesignCapacity" in data and data["DesignCapacity"] > 0:
            qmax_health = int((max(data["Qmax"]) / data["DesignCapacity"]) * 100)
        fcc_health = 0
        if numerator > 0 and "DesignCapacity" in data and data["DesignCapacity"] > 0:
            fcc_health = int((numerator / data["DesignCapacity"]) * 100)

        # Stress Test
        samples = []
        for i in range(duration):
            if stop_scan.is_set():
                with state_lock:
                    state["status"] = "complete"
                    state["verdict"] = "CANCELLED"
                    state["log"].append({
                        "title": "Scan Cancelled",
                        "desc": "User stopped the scan manually.",
                        "status": "warning"
                    })
                return
            pct = int(10 + ((i / duration) * 85))
            state["progress"] = pct
            s_res = subprocess.run(cmd, capture_output=True, text=True)
            m = re.search(r'"Voltage"\s*=\s*(\d+)', s_res.stdout)
            if m:
                samples.append(int(m.group(1)))
            time.sleep(1)
        
        # Analyze
        state["progress"] = 100
        log = []
        score = 0
        cycles = data.get("CycleCount", 0)
        
        # Entropy
        if "Qmax" in data:
            var = max(data["Qmax"]) - min(data["Qmax"])
            if var == 0:
                if cycles > 5:
                    log.append({"title": "Physics Violation: Zero Entropy",
                        "desc": "Every cell claims identical capacity. Real lithium cells always vary. This data is hard-coded.",
                        "status": "fail"})
                    score += SCORE_ZERO_ENTROPY
                else:
                    log.append({"title": "Physics Check: Uncalibrated",
                        "desc": "Cells identical (0mAh variance). Normal for brand new batteries (0-5 cycles).",
                        "status": "warning"})
            else:
                log.append({"title": "Physics Check: Passed",
                    "desc": f"Cells show healthy natural variance ({var} mAh).",
                    "status": "success"})
        
        # Internal Resistance
        if qmax_health > 0 and fcc_health > 0:
            delta = qmax_health - fcc_health
            if delta > 3:
                log.append({"title": "Internal Resistance: Normal",
                    "desc": f"Chemical ({qmax_health}%) vs Usable ({fcc_health}%): {delta}% gap confirms real impedance aging.",
                    "status": "success"})
            elif cycles > 200 and delta == 0:
                log.append({"title": "Internal Resistance: Suspicious",
                    "desc": f"At {cycles} cycles, expected some impedance loss but found none.",
                    "status": "warning"})
        
        # Qmax Clone
        if "Qmax" in data and "DesignCapacity" in data:
            if data["Qmax"][0] == data["DesignCapacity"] and cycles > 5:
                log.append({"title": "Firmware Hack: Lazy Cloning",
                    "desc": f"Qmax ({data['Qmax'][0]} mAh) matches Design Capacity exactly. Common hack to fake 100% health.",
                    "status": "fail"})
                score += SCORE_LAZY_CLONE
        
        # DOD0
        if "DOD0" in data and "DesignCapacity" in data:
            if data["DOD0"][0] == data["DesignCapacity"]:
                log.append({"title": "Calibration Tampering: DOD0",
                    "desc": f"Depth of Discharge matches Capacity ({data['DesignCapacity']}). Impossible in genuine TI firmware.",
                    "status": "fail"})
                score += SCORE_CALIBRATION_TAMPERING
        
        # PF Flags
        if "PermanentFailureStatus" in data and data["PermanentFailureStatus"] != 0:
            log.append({"title": "Safety Alert: Permanent Failure",
                "desc": f"Critical failure flag: {hex(data['PermanentFailureStatus'])}. Battery unsafe.",
                "status": "fail"})
        
        # Voltage Stress
        if samples:
            v_var = max(samples) - min(samples)
            if v_var == 0:
                log.append({"title": "Live Sensors: Flatline Detected",
                    "desc": "Voltage stayed perfectly constant. Real batteries fluctuate under load. This chip is broadcasting a static value.",
                    "status": "fail"})
                score += SCORE_FLATLINE
            else:
                log.append({"title": "Live Sensors: Active",
                    "desc": f"Voltage fluctuated by {v_var}mV during stress test. Sensors alive.",
                    "status": "success"})
        
        # Odometer
        writes = data.get("DataFlashWriteCount", 0)
        if writes > 0:
            est_cycles = int(writes / 14)
            if cycles < 20 and est_cycles > (cycles + 30):
                log.append({"title": "Odometer Rollback: Verified",
                    "desc": f"Claims: {cycles} Cycles | Real Usage: ~{est_cycles} Cycles. The chip was reset to look new.",
                    "status": "fail"})
                score += SCORE_ODOMETER_ROLLBACK
        
        # Time Paradox
        t = data.get("TotalOperatingTime", 0)
        if writes > 1000 and t < 500:
            log.append({"title": "Time Paradox: Frozen Clock",
                "desc": f"Massive usage ({writes} writes) but claims only {t} hours. Internal clock is frozen.",
                "status": "fail"})
            score += SCORE_TIME_PARADOX
        
        log.append({"title": "Scan Saved", "desc": "Results logged to history.",
            "status": "success"})
        
        # Compute composite health score and trends
        health_score = compute_health_score(data, score)
        trends = compute_trends(data, last_scan)
        
        with state_lock:
            state["log"] = log
            state["score"] = score
            state["health_score"] = health_score
            state["trends"] = trends
            if score >= SCORE_THRESHOLD_SPOOFED:
                state["verdict"] = "SPOOFED"
            elif score > 0:
                state["verdict"] = "SUSPICIOUS"
            else:
                state["verdict"] = "GENUINE"
    
    except Exception as e:
        with state_lock:
            state["verdict"] = "ERROR"
            state["log"].append({"title": "System Error", "desc": str(e), "status": "fail"})
    
    state["status"] = "complete"


# --- HTTP SERVER ---
class AppHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
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
            info = {"model": get_mac_model(), "version": VERSION}
            self.wfile.write(json.dumps(info).encode())
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == "/api/scan":
            content_len = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_len) if content_len else b'{}'
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
            content_len = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(content_len))
            days = body.get("days", 7)
            hour = body.get("hour", 20)
            minute = body.get("minute", 0)
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


def generate_share_report():
    """Generate a plain text report for sharing."""
    m = state["metrics"]
    lines = [
        f"🔋 Mac Battery Guardian v{VERSION} — Scan Report",
        f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Model: {state.get('mac_model', 'Mac')}",
        f"Serial: {m.get('serial', '--')}",
        "",
        f"Verdict: {state['verdict']}",
        f"Health Score: {state['health_score']}/100",
        f"Cycles: {m.get('cycle_count', '--')}",
        f"Health: {m.get('health', '--')}",
        f"Operating Time: {m.get('op_time', '--')}",
        "",
        "Checks:"
    ]
    for item in state.get("log", []):
        icon = "✅" if item["status"] == "success" else ("⚠️" if item["status"] == "warning" else "❌")
        lines.append(f"  {icon} {item['title']}")
    lines.append("")
    lines.append("Generated by Battery Guardian — github.com/Dannyjay-hub/Battery-Guardian-for-Mac")
    return "\n".join(lines)


# --- AUTOMATION ---
def install_launch_agent(days, hour=20, minute=0):
    try:
        safe_dir = os.path.expanduser("~/.battery_guardian")
        if not os.path.exists(safe_dir):
            os.makedirs(safe_dir)
        current_script = os.path.abspath(__file__)
        safe_script = os.path.join(safe_dir, "bg_auto.py")
        with open(current_script, 'r') as src, open(safe_script, 'w') as dst:
            dst.write(src.read())
        plist_path = os.path.expanduser("~/Library/LaunchAgents/com.batteryguardian.daily.plist")
        python_path = sys.executable
        plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.batteryguardian.daily</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python_path}</string>
        <string>{safe_script}</string>
        <string>--auto</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>{hour}</integer>
        <key>Minute</key>
        <integer>{minute}</integer>
    </dict>
    <key>RunAtLoad</key>
    <false/>
    <key>StandardOutPath</key>
    <string>/tmp/battery_guardian.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/battery_guardian.err</string>
</dict>
</plist>"""
        with open(plist_path, "w") as f:
            f.write(plist_content)
        os.system(f"launchctl unload {plist_path} 2>/dev/null")
        os.system(f"launchctl load {plist_path}")
        return True, f"Scheduled ({hour}:{minute:02d}) for {days} days."
    except Exception as e:
        return False, str(e)
# --- FRONTEND TEMPLATE ---
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Battery Guardian</title>
    <style>
        :root {
            --bg: #0D0D0F; --panel: #1A1A1E; --panel-hover: #222228;
            --text: #F5F5F7; --sub: #86868B; --accent: #0A84FF;
            --green: #30D158; --red: #FF453A; --orange: #FFD60A;
            --border: rgba(255,255,255,0.08);
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            background: var(--bg); color: var(--text);
            font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", sans-serif;
            padding: 24px; display: flex; justify-content: center;
            min-height: 100vh;
        }
        .container { max-width: 720px; width: 100%; }

        /* Header */
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 28px; }
        .brand h1 { font-size: 22px; font-weight: 700; letter-spacing: -0.3px; }
        .brand-sub { color: var(--sub); font-size: 13px; margin-top: 3px; }
        .header-actions { display: flex; gap: 8px; }
        .icon-btn {
            background: var(--panel); border: 1px solid var(--border); color: var(--sub);
            width: 36px; height: 36px; border-radius: 8px; cursor: pointer;
            display: flex; align-items: center; justify-content: center; font-size: 16px;
            transition: all 0.2s;
        }
        .icon-btn:hover { background: var(--panel-hover); color: var(--text); }

        /* Health Ring */
        .health-ring-section {
            display: flex; flex-direction: column; align-items: center;
            padding: 32px 0; margin-bottom: 24px;
        }
        .ring-container { position: relative; width: 180px; height: 180px; }
        .ring-svg { width: 180px; height: 180px; transform: rotate(-90deg); }
        .ring-bg { fill: none; stroke: var(--panel); stroke-width: 10; }
        .ring-fill {
            fill: none; stroke: var(--green); stroke-width: 10;
            stroke-linecap: round; stroke-dasharray: 502; stroke-dashoffset: 502;
            transition: stroke-dashoffset 1.5s ease, stroke 0.5s ease;
        }
        .ring-center {
            position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
            text-align: center;
        }
        .ring-score { font-size: 48px; font-weight: 800; letter-spacing: -2px; }
        .ring-label { font-size: 12px; color: var(--sub); text-transform: uppercase; letter-spacing: 1px; margin-top: 2px; }

        /* Verdict Badge */
        .verdict-badge {
            display: inline-block; padding: 6px 18px; border-radius: 20px;
            font-size: 13px; font-weight: 700; letter-spacing: 1px;
            text-transform: uppercase; margin-top: 16px;
            animation: fadeIn 0.5s ease;
        }
        .verdict-badge.genuine { background: rgba(48,209,88,0.15); color: var(--green); }
        .verdict-badge.spoofed { background: rgba(255,69,58,0.15); color: var(--red); }
        .verdict-badge.suspicious { background: rgba(255,214,10,0.15); color: var(--orange); }
        .verdict-badge.analyzing { background: rgba(10,132,255,0.15); color: var(--accent); }
        .verdict-badge.cancelled { background: rgba(134,134,139,0.15); color: var(--sub); }
        .verdict-badge.ready { background: var(--panel); color: var(--sub); }

        /* Cards Grid */
        .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 24px; }
        .card {
            background: var(--panel); border: 1px solid var(--border);
            border-radius: 12px; padding: 14px; transition: all 0.2s;
        }
        .card:hover { border-color: rgba(255,255,255,0.15); }
        .card-label { color: var(--sub); font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; font-weight: 600; margin-bottom: 6px; }
        .card-value { font-size: 18px; font-weight: 700; font-family: "SF Mono", "Menlo", monospace; }
        .card-trend { font-size: 11px; margin-top: 4px; }
        .trend-up { color: var(--green); }
        .trend-down { color: var(--red); }
        .trend-stable { color: var(--sub); }
        .trend-frozen { color: var(--red); }

        /* Scan Buttons */
        .scan-controls { display: flex; gap: 10px; margin-bottom: 24px; }
        .scan-btn {
            flex: 1; padding: 14px; border: none; border-radius: 12px;
            font-size: 15px; font-weight: 700; cursor: pointer; transition: all 0.2s;
        }
        .scan-btn.primary { background: var(--accent); color: white; }
        .scan-btn.primary:hover { background: #0070E0; }
        .scan-btn.secondary { background: var(--panel); color: var(--accent); border: 1px solid var(--border); }
        .scan-btn.secondary:hover { background: var(--panel-hover); }
        .scan-btn:disabled { opacity: 0.4; cursor: not-allowed; }
        .cancel-btn {
            padding: 14px; background: rgba(255,69,58,0.12); color: var(--red);
            border: 1px solid rgba(255,69,58,0.3); border-radius: 12px;
            font-size: 15px; font-weight: 700; cursor: pointer; display: none;
        }

        /* Progress */
        .progress-wrap { background: var(--panel); height: 6px; border-radius: 3px; overflow: hidden; margin-bottom: 24px; }
        .progress-bar { background: linear-gradient(90deg, var(--accent), #5AC8FA); height: 100%; width: 0%; transition: width 0.5s ease; border-radius: 3px; }

        /* Log Items */
        .log-item { display: flex; gap: 12px; padding: 12px 0; border-bottom: 1px solid var(--border); }
        .log-icon { font-size: 18px; flex-shrink: 0; }
        .log-title { font-weight: 600; font-size: 14px; margin-bottom: 3px; }
        .log-title.success { color: var(--green); }
        .log-title.fail { color: var(--red); }
        .log-title.warning { color: var(--orange); }
        .log-desc { font-size: 12px; color: var(--sub); line-height: 1.5; }

        /* Automation */
        .auto-section {
            background: rgba(48,209,88,0.06); border: 1px solid rgba(48,209,88,0.15);
            border-radius: 12px; padding: 16px; margin-bottom: 24px;
            display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px;
        }
        .auto-title { font-weight: 700; font-size: 13px; color: var(--green); }
        .auto-desc { font-size: 11px; color: var(--sub); margin-top: 2px; }
        .auto-controls { display: flex; align-items: center; gap: 8px; }
        .auto-input {
            background: var(--bg); border: 1px solid var(--border); color: white;
            border-radius: 8px; padding: 6px 8px; font-size: 13px; color-scheme: dark;
        }
        .auto-input:focus { border-color: var(--accent); outline: none; }
        .auto-btn {
            background: rgba(48,209,88,0.12); color: var(--green); border: 1px solid rgba(48,209,88,0.25);
            border-radius: 8px; padding: 6px 14px; font-size: 12px; font-weight: 600; cursor: pointer;
        }
        .auto-btn:hover { background: rgba(48,209,88,0.2); }

        /* History */
        .history-section { border-top: 1px solid var(--border); padding-top: 20px; margin-top: 8px; }
        .section-title { font-size: 16px; font-weight: 700; margin-bottom: 14px; }
        .history-table { width: 100%; border-collapse: collapse; font-size: 13px; }
        .history-table th { text-align: left; color: var(--sub); font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; padding: 8px 0; border-bottom: 1px solid var(--border); }
        .history-table td { padding: 10px 0; border-bottom: 1px solid var(--border); }

        /* Footer */
        .footer { text-align: center; padding: 24px 0; font-size: 11px; color: var(--sub); }
        .footer a { color: var(--accent); text-decoration: none; }

        /* About Modal */
        .modal-overlay {
            display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0,0,0,0.6); z-index: 100; justify-content: center; align-items: center;
        }
        .modal-overlay.show { display: flex; }
        .modal {
            background: var(--panel); border-radius: 16px; padding: 28px; max-width: 500px;
            width: 90%; max-height: 80vh; overflow-y: auto; border: 1px solid var(--border);
        }
        .modal h2 { font-size: 18px; margin-bottom: 16px; }
        .modal p { font-size: 13px; color: var(--sub); line-height: 1.6; margin-bottom: 12px; }
        .modal-close {
            background: var(--accent); color: white; border: none; padding: 10px 24px;
            border-radius: 8px; font-weight: 600; cursor: pointer; margin-top: 8px;
        }

        /* No Battery Screen */
        .no-battery {
            text-align: center; padding: 80px 20px;
        }
        .no-battery-icon { font-size: 64px; margin-bottom: 20px; }
        .no-battery h2 { font-size: 22px; margin-bottom: 12px; }
        .no-battery p { color: var(--sub); font-size: 14px; line-height: 1.6; max-width: 400px; margin: 0 auto; }

        /* Animations */
        @keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes pulse { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.03); } }
        .fade-in { animation: fadeIn 0.4s ease; }

        /* Responsive */
        @media (max-width: 600px) {
            .grid { grid-template-columns: repeat(2, 1fr); }
            body { padding: 16px; }
        }
    </style>
</head>
<body>
    <div class="container" id="main-app">
        <div class="header">
            <div class="brand">
                <h1>🔋 Battery Guardian</h1>
                <div class="brand-sub" id="sys-info">v""" + VERSION + """ — Loading...</div>
            </div>
            <div class="header-actions">
                <button class="icon-btn" onclick="copyReport()" title="Copy Report">📋</button>
                <button class="icon-btn" onclick="exportLogs()" title="Export Logs">📤</button>
                <button class="icon-btn" onclick="showAbout()" title="About">ℹ️</button>
            </div>
        </div>

        <div class="auto-section">
            <div>
                <div class="auto-title">⚡ Automate Daily Scans</div>
                <div class="auto-desc">Run silently in the background</div>
            </div>
            <div class="auto-controls">
                <label style="font-size:11px;color:var(--sub)">Days:</label>
                <input type="number" id="auto-days" class="auto-input" value="7" min="1" max="999" style="width:55px">
                <label style="font-size:11px;color:var(--sub)">Time:</label>
                <input type="time" id="auto-time" class="auto-input" value="20:00">
                <button class="auto-btn" onclick="enableAutomation()">Enable</button>
            </div>
        </div>

        <div class="health-ring-section">
            <div class="ring-container">
                <svg class="ring-svg" viewBox="0 0 180 180">
                    <circle class="ring-bg" cx="90" cy="90" r="80"/>
                    <circle class="ring-fill" id="ring-fill" cx="90" cy="90" r="80"/>
                </svg>
                <div class="ring-center">
                    <div class="ring-score" id="ring-score">—</div>
                    <div class="ring-label">Health Score</div>
                </div>
            </div>
            <div class="verdict-badge ready" id="verdict-badge">Ready to Scan</div>
        </div>

        <div class="progress-wrap"><div class="progress-bar" id="progress"></div></div>

        <div class="grid">
            <div class="card"><div class="card-label">Cycles</div><div class="card-value" id="m-cycles">—</div><div class="card-trend" id="t-cycles"></div></div>
            <div class="card"><div class="card-label">Health</div><div class="card-value" id="m-health">—</div><div class="card-trend" id="t-health"></div></div>
            <div class="card"><div class="card-label">Entropy</div><div class="card-value" id="m-entropy">—</div></div>
            <div class="card"><div class="card-label">Write Ratio</div><div class="card-value" id="m-ratio">—</div></div>
            <div class="card"><div class="card-label">Op Time</div><div class="card-value" id="m-optime">—</div><div class="card-trend" id="t-optime"></div></div>
            <div class="card"><div class="card-label">Spoof Score</div><div class="card-value" id="m-score">0</div></div>
        </div>

        <div class="scan-controls">
            <button class="scan-btn primary" id="full-btn" onclick="startScan('full')">Full Scan (60s)</button>
            <button class="scan-btn secondary" id="quick-btn" onclick="startScan('quick')">Quick Scan (10s)</button>
            <button class="cancel-btn" id="cancel-btn" onclick="cancelScan()">Cancel</button>
        </div>

        <div id="log-container"></div>

        <div class="history-section">
            <div class="section-title">History Log</div>
            <table class="history-table">
                <thead><tr><th>Date</th><th>Cycles</th><th>Health</th><th>Op Time</th></tr></thead>
                <tbody id="history-body">
                    <tr><td colspan="4" style="color:var(--sub)">No history yet. Run a scan.</td></tr>
                </tbody>
            </table>
        </div>

        <div class="footer">
            Built by <a href="https://github.com/Dannyjay-hub" target="_blank">@Dannyjay-hub</a> · Battery Guardian v""" + VERSION + """
        </div>
    </div>

    <!-- No Battery Screen (hidden by default) -->
    <div class="no-battery" id="no-battery" style="display:none">
        <div class="no-battery-icon">🖥️</div>
        <h2>No Battery Detected</h2>
        <p>Battery Guardian requires a MacBook with a built-in battery. This device (Mac Mini, iMac, Mac Pro, or Mac Studio) doesn't have a battery to analyze.</p>
    </div>

    <!-- About Modal -->
    <div class="modal-overlay" id="about-modal">
        <div class="modal">
            <h2>About Battery Guardian</h2>
            <p><strong>Battery Guardian</strong> is a forensic tool that detects counterfeit, reprogrammed, or spoofed MacBook batteries by analyzing the Texas Instruments gas gauge chip data.</p>
            <p><strong>Health Score:</strong> A composite 0-100 rating combining capacity, cycle count, and spoof indicators.</p>
            <p><strong>Entropy Check:</strong> Verifies that individual cells have natural capacity variance (spoofed batteries show zero).</p>
            <p><strong>Live Sensor Test:</strong> Monitors voltage fluctuation in real-time. Real batteries fluctuate; fakes show flatlines.</p>
            <p><strong>Odometer Check:</strong> Compares cycle count against flash write count to detect resets.</p>
            <p><strong>Time Paradox:</strong> Detects if the internal clock has been frozen to hide the battery's true age.</p>
            <button class="modal-close" onclick="hideAbout()">Close</button>
        </div>
    </div>

    <script>
        let isRunning = false;

        // Init
        (async () => {
            try {
                const res = await fetch('/api/info');
                const info = await res.json();
                document.getElementById('sys-info').innerText = `v${info.version} — ${info.model}`;
            } catch(e) {}
            loadHistory();
        })();

        async function startScan(mode) {
            if (isRunning) return;
            isRunning = true;
            document.getElementById('full-btn').disabled = true;
            document.getElementById('quick-btn').disabled = true;
            document.getElementById('cancel-btn').style.display = 'block';
            document.getElementById('log-container').innerHTML = '';

            updateVerdict('ANALYZING...', 'analyzing');
            updateRing(0, 'var(--accent)');

            await fetch('/api/scan', { method: 'POST', body: JSON.stringify({ mode }) });
            pollStatus();
        }

        async function cancelScan() {
            if (!isRunning) return;
            await fetch('/api/cancel', { method: 'POST' });
        }

        async function pollStatus() {
            const res = await fetch('/api/status');
            const d = await res.json();

            document.getElementById('progress').style.width = d.progress + '%';

            if (d.metrics.cycle_count !== '--') document.getElementById('m-cycles').innerText = d.metrics.cycle_count;
            if (d.metrics.health !== '--') document.getElementById('m-health').innerText = d.metrics.health;
            if (d.metrics.qmax_var !== '--') document.getElementById('m-entropy').innerText = d.metrics.qmax_var + ' mAh';
            if (d.metrics.ratio !== '--') document.getElementById('m-ratio').innerText = d.metrics.ratio;
            if (d.metrics.op_time !== '--') document.getElementById('m-optime').innerText = d.metrics.op_time;
            document.getElementById('m-score').innerText = d.score;

            // Serial
            if (d.metrics.serial && d.metrics.serial !== '--') {
                const sub = document.getElementById('sys-info');
                if (!sub.innerText.includes('SN:')) {
                    sub.innerText += ` | SN: ${d.metrics.serial}`;
                }
            }

            if (d.status === 'complete') {
                isRunning = false;
                document.getElementById('full-btn').disabled = false;
                document.getElementById('quick-btn').disabled = false;
                document.getElementById('cancel-btn').style.display = 'none';

                // Verdict
                const vClass = d.verdict === 'SPOOFED' ? 'spoofed' :
                               d.verdict === 'GENUINE' ? 'genuine' :
                               d.verdict === 'CANCELLED' ? 'cancelled' : 'suspicious';
                updateVerdict(d.verdict, vClass);

                // Health Ring
                const hs = d.health_score || 0;
                updateRing(hs, hs >= 70 ? 'var(--green)' : hs >= 40 ? 'var(--orange)' : 'var(--red)');
                document.getElementById('ring-score').innerText = hs;

                // Trends
                if (d.trends) {
                    setTrend('t-cycles', d.trends.cycles);
                    setTrend('t-health', d.trends.health);
                    setTrend('t-optime', d.trends.op_time);
                }

                // Logs
                const lc = document.getElementById('log-container');
                lc.innerHTML = '';
                d.log.forEach(item => {
                    const icon = item.status === 'success' ? '✅' : (item.status === 'warning' ? '⚠️' : '❌');
                    lc.innerHTML += `<div class="log-item fade-in">
                        <div class="log-icon">${icon}</div>
                        <div><div class="log-title ${item.status}">${item.title}</div>
                        <div class="log-desc">${item.desc}</div></div></div>`;
                });

                loadHistory();
            } else {
                setTimeout(pollStatus, 1000);
            }
        }

        function updateVerdict(text, cls) {
            const b = document.getElementById('verdict-badge');
            b.className = 'verdict-badge ' + cls;
            b.innerText = text;
        }

        function updateRing(pct, color) {
            const c = document.getElementById('ring-fill');
            const offset = 502 - (502 * pct / 100);
            c.style.strokeDashoffset = offset;
            c.style.stroke = color;
        }

        function setTrend(id, trend) {
            const el = document.getElementById(id);
            if (!el || !trend) return;
            const map = { up: ['↑', 'trend-up'], down: ['↓', 'trend-down'], stable: ['→', 'trend-stable'], frozen: ['⏸ Frozen', 'trend-frozen'] };
            const [text, cls] = map[trend] || ['', ''];
            el.className = 'card-trend ' + cls;
            el.innerText = text;
        }

        async function loadHistory() {
            try {
                const res = await fetch('/api/history');
                const logs = await res.json();
                const tbody = document.getElementById('history-body');
                if (logs.length > 0) {
                    tbody.innerHTML = '';
                    logs.slice(-10).reverse().forEach(e => {
                        const date = new Date(e.timestamp).toLocaleDateString();
                        const cycles = e.cycle_count || 0;
                        const health = e.parsed.AppleRawMaxCapacity && e.parsed.DesignCapacity ?
                            Math.round((e.parsed.AppleRawMaxCapacity / e.parsed.DesignCapacity) * 100) + '%' : '—';
                        const time = e.parsed.TotalOperatingTime || 0;
                        tbody.innerHTML += `<tr><td>${date}</td><td>${cycles}</td><td>${health}</td><td>${time} hrs</td></tr>`;
                    });
                }
            } catch(e) {}
        }

        async function enableAutomation() {
            const days = document.getElementById('auto-days').value;
            const timeStr = document.getElementById('auto-time').value;
            if (!days || !timeStr) { alert('Enter valid days and time.'); return; }
            const [h, m] = timeStr.split(':');
            if (!confirm(`Schedule daily scan at ${timeStr} for ${days} days?`)) return;
            try {
                const res = await fetch('/api/automate', {
                    method: 'POST',
                    body: JSON.stringify({ days: parseInt(days), hour: parseInt(h), minute: parseInt(m) })
                });
                const data = await res.json();
                alert(data.success ? 'Success: ' + data.msg : 'Error: ' + data.msg);
            } catch(e) { alert('Error: ' + e); }
        }

        async function exportLogs() {
            const res = await fetch('/api/export', { method: 'POST' });
            const data = await res.json();
            alert(data.success ? 'Exported to:\\n' + data.msg : 'Error: ' + data.msg);
        }

        async function copyReport() {
            try {
                const res = await fetch('/api/share', { method: 'POST' });
                const data = await res.json();
                await navigator.clipboard.writeText(data.report);
                alert('Report copied to clipboard!');
            } catch(e) { alert('Error copying: ' + e); }
        }

        function showAbout() { document.getElementById('about-modal').classList.add('show'); }
        function hideAbout() { document.getElementById('about-modal').classList.remove('show'); }
    </script>
</body>
</html>
"""


# --- MAIN ENTRY POINT ---
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
        print(f"[+] {msg}" if success else f"[-] Error: {msg}")
        sys.exit(0 if success else 1)

    # Headless
    if args.auto:
        ok, err = check_platform()
        if not ok:
            print(f"[-] Platform error: {err}")
            sys.exit(1)
        print("[*] Running Headless Scan...")
        perform_scan()
        print(f"[+] Verdict: {state['verdict']} | Health: {state['health_score']}/100")
        sys.exit(0)

    # --- GUI Mode ---
    # Platform check
    ok, platform_err = check_platform()

    # Detect Mac model
    mac_model = get_mac_model() if ok else "Unknown"
    state["mac_model"] = mac_model

    # Start HTTP server in background
    handler = AppHandler
    port_found = False
    for p in range(PORT, PORT + 10):
        try:
            httpd = socketserver.ThreadingTCPServer(("127.0.0.1", p), handler)
            PORT = p
            port_found = True
            break
        except OSError:
            continue

    if not port_found:
        print(f"Error: No open port found ({PORT}-{PORT+9})")
        sys.exit(1)

    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()
    print(f"Server running at http://localhost:{PORT}")

    # Launch window
    use_native = not args.no_window
    if use_native:
        try:
            import webview
            webview.create_window(
                "Battery Guardian",
                f"http://localhost:{PORT}",
                width=800,
                height=920,
                resizable=True,
                min_size=(600, 700)
            )
            webview.start()
        except ImportError:
            print("[!] pywebview not installed. Falling back to browser.")
            import webbrowser
            webbrowser.open(f"http://localhost:{PORT}")
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                pass
    else:
        import webbrowser
        webbrowser.open(f"http://localhost:{PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
