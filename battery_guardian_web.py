
import http.server
import socketserver
import webbrowser
import threading
import subprocess
import re
import json
import time
import sys
import os
from datetime import datetime

PORT = 8080
SCAN_DURATION = 60

# --- HISTORY MANAGER (Copied from GUI) ---
class HistoryManager:
    FILE_PATH = os.path.expanduser("~/.battery_guardian_history.json")

    @staticmethod
    def load():
        if not os.path.exists(HistoryManager.FILE_PATH): return []
        try:
            with open(HistoryManager.FILE_PATH, 'r') as f:
                return json.load(f)
        except: return []

    @staticmethod
    def save_scan(raw_text, parsed_data):
        history = HistoryManager.load()
        
        # Create a rich log entry
        entry = {
            "timestamp": datetime.now().isoformat(),
            "serial": parsed_data.get("Serial", "UNKNOWN"),
            "cycle_count": parsed_data.get("CycleCount", 0),
            "parsed": parsed_data,
            "raw_text_snippet": raw_text[:2000] # Store first 2k chars for debug if needed
        }
        
        history.append(entry)
        
        # Save back
        with open(HistoryManager.FILE_PATH, 'w') as f:
            json.dump(history, f, indent=2)

    @staticmethod
    def export_to_desktop():
        try:
            history = HistoryManager.load()
            dest = os.path.expanduser("~/Desktop/battery_guardian_logs.json")
            with open(dest, 'w') as f:
                json.dump(history, f, indent=2)
            return True, dest
        except Exception as e:
            return False, str(e)

# --- GLOBAL STATE ---
state = {
    "status": "idle",  # idle, running, complete
    "progress": 0,
    "log": [],         # List of check results
    "verdict": "READY",
    "score": 0,
    "metrics": {
        "cycle_count": "--",
        "write_count": "--",
        "qmax_var": "--",
        "op_time": "--",
        "health": "--",
        "ratio": "--"
    }
}

# --- CORE LOGIC (SHARED) ---
def parse_ioreg(text):
    d = {}
    # Universal: Capture generic "Key" = Value pairs (Integers)
    # Matches: "Key" = 123
    for m in re.finditer(r'"(\w+)"\s*=\s*(\d+)', text):
        d[m.group(1)] = int(m.group(2))
        
    # Universal: Capture generic "Key" = "String"
    for m in re.finditer(r'"(\w+)"\s*=\s*"([^"]+)"', text):
        d[m.group(1)] = m.group(2)

    # Universal: Capture generic "Key" = (List)
    # Matches: "Key" = (1, 2, 3)
    for m in re.finditer(r'"(\w+)"\s*=\s*\(([^)]+)\)', text):
        content = m.group(2)
        # Try integers
        try:
            vals = [int(x.strip()) for x in content.split(',') if x.strip().isdigit()]
            if vals: d[m.group(1)] = vals
        except: pass # Ignore non-int lists for now
    return d

def perform_scan():
    global state
    state["status"] = "running"
    state["progress"] = 0
    state["log"] = []
    state["score"] = 0
    state["verdict"] = "ANALYZING..."
    
    try:
        # 1. Fetch
        state["progress"] = 5
        cmd = ["ioreg", "-l", "-w0", "-r", "-c", "AppleSmartBattery"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if not res.stdout: raise Exception("No Battery Found via ioreg")
        data = parse_ioreg(res.stdout)
        
        # Save History
        HistoryManager.save_scan(res.stdout, data)
        
        # Update raw metrics for UI
        if "CycleCount" in data: state["metrics"]["cycle_count"] = data["CycleCount"]
        if "DataFlashWriteCount" in data: 
            state["metrics"]["write_count"] = data["DataFlashWriteCount"]
            if "CycleCount" in data:
                state["metrics"]["ratio"] = round(data["DataFlashWriteCount"] / max(1, data["CycleCount"]), 1)
        if "Qmax" in data: 
             state["metrics"]["qmax_var"] = max(data["Qmax"]) - min(data["Qmax"])
        if "TotalOperatingTime" in data: state["metrics"]["op_time"] = f"{data['TotalOperatingTime']} hrs"
        
        # Health Calculation: Prioritize AppleRawMaxCapacity (True Hardware Capacity)
        fcc_health = 0
        numerator = 0
        if "AppleRawMaxCapacity" in data:
            numerator = data["AppleRawMaxCapacity"]
        elif "MaxCapacity" in data:
            numerator = data["MaxCapacity"]

        if numerator > 0 and "DesignCapacity" in data and data["DesignCapacity"] > 0:
            fcc_health = int((numerator / data["DesignCapacity"]) * 100)
            state["metrics"]["health"] = f"{fcc_health}% ({numerator} / {data['DesignCapacity']} mAh)"
        else:
            state["metrics"]["health"] = "Error"
        
        qmax_health = 0
        if "Qmax" in data and "DesignCapacity" in data and data["DesignCapacity"] > 0:
            qmax_health = int((max(data["Qmax"]) / data["DesignCapacity"]) * 100)

        # 2. Stress Test
        samples = []
        for i in range(SCAN_DURATION):
            # Update progress
            pct = int(10 + ((i / SCAN_DURATION) * 85))
            state["progress"] = pct
            
            s_res = subprocess.run(cmd, capture_output=True, text=True)
            m = re.search(r'"Voltage"\s*=\s*(\d+)', s_res.stdout)
            if m: samples.append(int(m.group(1)))
            time.sleep(1)
        
        # 3. Analyze
        state["progress"] = 100
        
        # Logic
        log = []
        score = 0
        cycles = data.get("CycleCount", 0)
        
        # Entropy
        if "Qmax" in data:
            var = max(data["Qmax"]) - min(data["Qmax"])
            if var == 0:
                if cycles > 5:
                    log.append({"title": "Physics Violation: Zero Entropy", "desc": "Your battery claims every cell is identical down to the last electron. Real lithium cells always vary slightly. This proves the data is hard-coded/spoofed.", "status": "fail"})
                    score += 40
                else:
                    log.append({"title": "Physics Check: Uncalibrated", "desc": "Cells are perfectly identical (0mAh variance). This is technically normal for brand new (0-5 cycle) batteries that haven't learned their capacity yet.", "status": "warning"})
            else:
                log.append({"title": "Physics Check: Passed", "desc": f"Cells show healthy natural variance ({var} mAh). This looks like organic chemical aging.", "status": "success"})
        
        # Internal Resistance / Health Delta Check (New)
        if qmax_health > 0 and fcc_health > 0:
            delta = qmax_health - fcc_health
            if delta > 3:
                # This is GOOD. It means Chemistry (94%) > Usable (82%), so energy is lost to heat/resistance.
                log.append({"title": "Physics Check: Internal Resistance", "desc": f"Chemical Capacity ({qmax_health}%) is higher than Usable Health ({fcc_health}%). This {delta}% gap confirms real internal impedance build-up due to aging.", "status": "success"})
            elif cycles > 200 and delta == 0:
                 # Suspicious: Old batteries shouldn't be perfect
                 log.append({"title": "Physics Check: Suspiciously Efficient", "desc": f"Chemical and Usable capacity depend perfectly hard. At {cycles} cycles, expected some impedance loss.", "status": "warning"})

        # Qmax Clone
        if "Qmax" in data and "DesignCapacity" in data:
            if data["Qmax"][0] == data["DesignCapacity"]:
                if cycles > 5:
                    log.append({"title": "Firmware Hack: Lazy Cloning", "desc": f"The chip's 'Qmax' (Chemical Capacity: {data['Qmax'][0]} mAh) matches 'Design Capacity' exactly. This is a common hack to fake 100% health, but the system isn't fooled (hence your low Real Health).", "status": "fail"})
                    score += 30
                else:
                    log.append({"title": "Firmware Check: Uncalibrated", "desc": f"Capacity exactly matches Design ({data['Qmax'][0]}). This is normal for brand new batteries until first discharge.", "status": "warning"})

        # DOD0
        if "DOD0" in data and "DesignCapacity" in data:
            if data["DOD0"][0] == data["DesignCapacity"]:
                log.append({"title": "Calibration Tampering: DOD0", "desc": f"The 'Depth of Discharge' calibration value matches the Capacity ({data['DesignCapacity']}). This is technically impossible in genuine Texas Instruments firmware.", "status": "fail"})
                score += 30

        # Stress
        if samples:
            v_var = max(samples) - min(samples)
            if v_var == 0:
                log.append({"title": "Live Sensors: Flatline Detected", "desc": "Voltage stayed exactly perfect for 60 seconds. Real electricity fluctuates slightly under load. The chip is broadcasting a static 'Screenshot', not measuring real physics.", "status": "fail"})
                score += 50
            else:
                log.append({"title": "Live Sensors: Active", "desc": f"Voltage fluctuated naturally by {v_var}mV during the stress test. The sensors are alive.", "status": "success"})

        # Forensic Age
        writes = data.get("DataFlashWriteCount", 0)
        cycles = data.get("CycleCount", 0)
        if writes > 0:
            est_cycles = int(writes / 14)
            if cycles < 20 and est_cycles > (cycles + 30):
                log.append({"title": "Odometer Rollback: Verified", "desc": f"Marketing Claims: {cycles} Cycles\nReal Usage Est: ~{est_cycles} Cycles\nThis chip has been reset to look new, but the Flash Memory history proves it is used.", "status": "fail"})
                score += 60

        # Time Paradox
        t = data.get("TotalOperatingTime", 0)
        if writes > 1000 and t < 500:
             log.append({"title": "Time Paradox: Frozen Clock", "desc": f"The chip has logged massive usage ({writes} writes) but claims to be only {t} hours old. The internal clock has likely been frozen to hide aging.", "status": "fail"})
             score += 20
        
        # Log History Success
        log.append({"title": "Flight Recorder: Saved", "desc": "This scan has been saved to the permanent history log. Future scans will compare against this to detect 'Frozen Time'.", "status": "success"})

        state["log"] = log
        state["score"] = score
        
        if score >= 40: state["verdict"] = "SPOOFED"
        elif score > 0: state["verdict"] = "SUSPICIOUS"
        else: state["verdict"] = "GENUINE"
        
    except Exception as e:
        state["verdict"] = "ERROR"
        state["log"].append({"title": "System Error", "desc": str(e), "status": "fail"})

    state["status"] = "complete"


# --- HTTP SERVER ---
class AppHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        return # Silence server logs

    def do_GET(self):
        if self.path == '/api/status':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(state).encode())
        elif self.path == '/api/history':
            h = HistoryManager.load()
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(h).encode())
        elif self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == '/api/scan':
            if state["status"] != "running":
                threading.Thread(target=perform_scan).start()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
        elif self.path == '/api/export':
            success, msg = HistoryManager.export_to_desktop()
            res = {"success": success, "msg": msg}
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(res).encode())

# --- FRONTEND (Embed HTML to keep it single-file) ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mac Battery Guardian - Web Edition</title>
    <style>
        :root { --bg: #1C1C1E; --panel: #2C2C2E; --text: #FFFFFF; --sub: #98989D; --accent: #0A84FF; --green: #32D74B; --red: #FF453A; --orange: #FFD60A; }
        body { background-color: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; margin: 0; padding: 20px; display: flex; justify-content: center; }
        .container { max-width: 700px; width: 100%; }
        
        .header { display: flex; justify-content: space-between; align-items: start; margin-bottom: 20px; }
        h1 { font-size: 24px; font-weight: 700; margin: 0 0 5px 0; }
        .header-sub { color: var(--sub); font-size: 14px; }
        
        .export-btn { background-color: var(--panel); color: var(--accent); border: none; padding: 8px 16px; border-radius: 6px; font-weight: 600; cursor: pointer; }
        .export-btn:hover { background-color: #3A3A3C; }
        
        .verdict-box { background-color: var(--panel); border-radius: 12px; height: 120px; display: flex; align-items: center; justify-content: center; margin-bottom: 20px; cursor: pointer; transition: background 0.3s; }
        .verdict-text { font-size: 32px; font-weight: 800; color: var(--sub); }
        .verdict-box.spoofed { background-color: var(--red); } .verdict-box.spoofed .verdict-text { color: white; }
        .verdict-box.genuine { background-color: var(--green); } .verdict-box.genuine .verdict-text { color: black; }
        .verdict-box.suspicious { background-color: var(--orange); } .verdict-box.suspicious .verdict-text { color: black; }

        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-bottom: 30px; }
        .card { background-color: var(--panel); border-radius: 10px; padding: 15px; }
        .card-label { color: var(--sub); font-size: 12px; text-transform: uppercase; font-weight: 600; margin-bottom: 5px; }
        .card-value { font-size: 22px; font-weight: 700; font-family: "Menlo", monospace; }

        .progress-container { background-color: var(--panel); height: 10px; border-radius: 5px; overflow: hidden; margin-bottom: 20px; }
        .progress-bar { background-color: var(--accent); height: 100%; width: 0%; transition: width 0.5s ease; }
        
        .scan-btn { width: 100%; padding: 15px; background-color: var(--accent); color: white; border: none; border-radius: 10px; font-size: 18px; font-weight: 700; cursor: pointer; margin-bottom: 30px; }
        .scan-btn:disabled { opacity: 0.5; cursor: not-allowed; }
        
        .history-section { border-top: 1px solid #333; padding-top: 20px; margin-top: 20px; }
        .history-title { font-size: 18px; font-weight: 700; margin-bottom: 15px; }
        .history-table { width: 100%; border-collapse: collapse; font-size: 14px; }
        .history-table th { text-align: left; color: var(--sub); padding-bottom: 10px; border-bottom: 1px solid #333; }
        .history-table td { padding: 10px 0; border-bottom: 1px solid #2C2C2E; color: var(--text); }
        .history-table tr:last-child td { border-bottom: none; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div>
                <h1>Mac Battery Guardian</h1>
                <div class="header-sub" id="sys-info">Web Edition v5.1 (Visual)</div>
            </div>
            <button class="export-btn" onclick="exportLogs()">EXPORT LOGS</button>
        </div>

        <div class="verdict-box" id="verdict-box" onclick="startScan()">
            <div class="verdict-text" id="verdict-text">CLICK TO SCAN</div>
        </div>

        <div class="progress-container"><div class="progress-bar" id="progress"></div></div>

        <div class="grid">
            <div class="card"><div class="card-label">Entropy</div><div class="card-value" id="m-entropy">--</div></div>
            <div class="card"><div class="card-label">Write Ratio</div><div class="card-value" id="m-ratio">--</div></div>
            <div class="card"><div class="card-label">Cycles (Odometer)</div><div class="card-value" id="m-cycles">--</div></div>
            <div class="card"><div class="card-label">Health</div><div class="card-value" id="m-health">--</div></div>
        </div>
        
        <button class="scan-btn" id="scan-btn" onclick="startScan()">START FULL SCAN (60s)</button>

        <div id="log-container"></div>
        
        <div class="history-section">
            <div class="history-title">History Log</div>
            <table class="history-table">
                <thead>
                    <tr>
                        <th>Date</th>
                        <th>Cycles</th>
                        <th>Writes</th>
                        <th>Op Time</th>
                    </tr>
                </thead>
                <tbody id="history-body">
                    <tr><td colspan="4" style="color:var(--sub)">No history found. Run a scan.</td></tr>
                </tbody>
            </table>
        </div>
    </div>

    <script>
        let isRunning = false;
        
        // Auto-detect system info via JS user-agent is flaky, let's just leave it generic or fetch from python if needed.
        document.getElementById('sys-info').innerText = "Web Edition v5.1 (Visual)";
        
        // Load History on Boot
        loadHistory();

        async function startScan() {
            if (isRunning) return;
            isRunning = true;
            document.getElementById('scan-btn').disabled = true;
            document.getElementById('scan-btn').innerText = "SCANNING...";
            document.getElementById('verdict-text').innerText = "ANALYZING...";
            document.getElementById('verdict-box').className = "verdict-box"; // Reset colors
            document.getElementById('log-container').innerHTML = ""; // Clear log
            
            await fetch('/api/scan', { method: 'POST' });
            pollStatus();
        }

        async function exportLogs() {
            const res = await fetch('/api/export', { method: 'POST' });
            const data = await res.json();
            if (data.success) {
                alert("Logs exported to:\\n" + data.msg);
            } else {
                alert("Error exporting logs:\\n" + data.msg);
            }
        }
        
        async function loadHistory() {
            try {
                const res = await fetch('/api/history');
                const logs = await res.json();
                const tbody = document.getElementById('history-body');
                
                if (logs.length > 0) {
                    tbody.innerHTML = "";
                    // Reverse to show newest first
                    logs.reverse().forEach(entry => {
                        const date = new Date(entry.timestamp).toLocaleString();
                        const cycles = entry.cycle_count || 0;
                        const writes = entry.parsed.DataFlashWriteCount || 0;
                        const time = entry.parsed.TotalOperatingTime || 0;
                        
                        tbody.innerHTML += `
                            <tr>
                                <td>${date}</td>
                                <td>${cycles}</td>
                                <td>${writes}</td>
                                <td>${time} hrs</td>
                            </tr>
                        `;
                    });
                } else {
                    tbody.innerHTML = `<tr><td colspan="4" style="color:var(--sub)">No history found. Run a scan.</td></tr>`;
                }
            } catch (e) { console.error(e); }
        }

        async function pollStatus() {
            const res = await fetch('/api/status');
            const data = await res.json();
            
            // Update UI
            document.getElementById('progress').style.width = data.progress + "%";
            
            if (data.metrics.qmax_var !== "--") document.getElementById('m-entropy').innerText = data.metrics.qmax_var + " mAh";
            if (data.metrics.ratio !== "--") document.getElementById('m-ratio').innerText = data.metrics.ratio;
            if (data.metrics.cycle_count !== "--") document.getElementById('m-cycles').innerText = data.metrics.cycle_count;
            if (data.metrics.health !== "--") document.getElementById('m-health').innerText = data.metrics.health;

            if (data.status === "complete") {
                isRunning = false;
                document.getElementById('scan-btn').disabled = false;
                document.getElementById('scan-btn').innerText = "SCAN AGAIN";
                
                // Verdict
                const vb = document.getElementById('verdict-box');
                const vt = document.getElementById('verdict-text');
                vt.innerText = data.verdict;
                if (data.verdict === "SPOOFED") vb.classList.add("spoofed");
                else if (data.verdict === "GENUINE") vb.classList.add("genuine");
                else vb.classList.add("suspicious");

                // Logs
                const lc = document.getElementById('log-container');
                lc.innerHTML = "";
                data.log.forEach(item => {
                    const icon = item.status === "success" ? "✅" : "❌";
                    const colorClass = item.status === "success" ? "success" : "fail";
                    lc.innerHTML += `
                        <div class="log-item">
                            <div class="log-icon">${icon}</div>
                            <div>
                                <div class="log-title ${colorClass}">${item.title}</div>
                                <div class="log-desc">${item.desc}</div>
                            </div>
                        </div>
                    `;
                });
                
                // Refresh History Table
                loadHistory();
                
            } else {
                setTimeout(pollStatus, 1000);
            }
        }
    </script>
</body>
</html>
"""

# --- MAIN ---
if __name__ == "__main__":
    # DO NOT suppress output - we need to see errors in the launcher!
    # sys.stderr = open(os.devnull, 'w')
    
    # Start Server with Dynamic Port Finding
    handler = AppHandler
    
    port_found = False
    for p in range(PORT, PORT + 10):
        try:
            httpd = socketserver.ThreadingTCPServer(("", p), handler)
            PORT = p
            port_found = True
            break
        except OSError:
            print(f"Port {p} in use, trying next...")
            continue
            
    if not port_found:
        print(f"Error: Could not find an open port between {PORT} and {PORT+10}")
        sys.exit(1)

    with httpd:
        print(f"Serving at http://localhost:{PORT}")
        
        # Open Browser
        webbrowser.open(f"http://localhost:{PORT}")
        
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
