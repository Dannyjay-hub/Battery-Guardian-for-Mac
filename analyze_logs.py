import json
import os
import sys
import datetime
import statistics

class LogAnalyzer:
    def __init__(self, history_path=None):
        if history_path:
            self.history_path = history_path
        else:
            self.history_path = os.path.expanduser("~/.battery_guardian_history.json")
        self.data = []

    def load_logs(self):
        """Loads the JSON history file."""
        if not os.path.exists(self.history_path):
            print(f"[!] No history file found at {self.history_path}")
            return False
        
        try:
            with open(self.history_path, 'r') as f:
                self.data = json.load(f)
            print(f"[*] Loaded {len(self.data)} log entries.")
            return True
        except Exception as e:
            print(f"[!] Error loading logs: {e}")
            return False

    def detect_flatlines(self, window_size=5):
        """
        Detects 'Flatlines': Periods where Voltage or Current stays EXACTLY the same.
        Real batteries fluctuate (noise) even when idle. Emulators output perfect constants.
        """
        print("\n--- FLATLINE ANALYSIS (Voltage Hard-Lock Check) ---")
        
        # Extract voltage series with timestamps
        series = []
        for entry in self.data:
            if "parsed" in entry and "Voltage" in entry["parsed"]:
                ts = datetime.datetime.fromisoformat(entry["timestamp"])
                volts = entry["parsed"]["Voltage"]
                series.append((ts, volts))
        
        if len(series) < window_size:
            print("[!] Not enough data points to detect flatlines (Need > 5).")
            return

        flatline_count = 0
        longest_streak = 0
        current_streak = 1
        
        for i in range(1, len(series)):
            prev_volts = series[i-1][1]
            curr_volts = series[i][1]
            
            if curr_volts == prev_volts:
                current_streak += 1
            else:
                if current_streak >= window_size:
                    flatline_count += 1
                    duration = series[i-1][0] - series[i-current_streak][0]
                    print(f"[!] FLATLINE DETECTED: {current_streak} samples ({duration}) at {prev_volts}mV")
                
                longest_streak = max(longest_streak, current_streak)
                current_streak = 1
                
        print(f"[*] Max Voltage Lock Streak: {longest_streak} samples")
        if longest_streak > 20: 
            print("[!!!] VERDICT: HIGH likelihood of Emulator/Spoof (Nature is rarely this perfect).")

    def detect_time_paradox(self):
        """
        Detects if 'TotalOperatingTime' is frozen while real time passes.
        """
        print("\n--- TIME PARADOX CHECK ---")
        if len(self.data) < 2: return

        first = self.data[0]
        last = self.data[-1]

        if "parsed" not in first or "parsed" not in last: return
        
        t1 = first["parsed"].get("TotalOperatingTime", 0)
        t2 = last["parsed"].get("TotalOperatingTime", 0)
        
        real_time_delta = datetime.datetime.fromisoformat(last["timestamp"]) - datetime.datetime.fromisoformat(first["timestamp"])
        
        # TotalOperatingTime unit varies, but usually it's hours or minutes. 
        # For this check, we just look for "Zero Change" over "Long Duration".
        
        print(f"[*] Real Time Elapsed: {real_time_delta}")
        print(f"[*] Battery Reported Time Elapsed: {t2 - t1} units")
        
        if (t2 - t1) == 0 and real_time_delta.total_seconds() > 3600:
             print("[!!!] TIME FREEZE DETECTED: 1+ hour passed but battery internal clock did not move 1 single unit.")
        elif (t2 - t1) == 0 and real_time_delta.total_seconds() > 600:
             print("[!] SUSPICIOUS: 10 minutes passed with no clock update.")

    def run(self):
        if self.load_logs():
            self.detect_flatlines()
            self.detect_time_paradox()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        path = sys.argv[1]
        print(f"[*] Analyzing custom log file: {path}")
        analyzer = LogAnalyzer(path)
    else:
        analyzer = LogAnalyzer()
    analyzer.run()
