"""Battery Guardian — main scan engine."""

import re
import subprocess
import time

from bg_config import (
    SCAN_DURATION_FULL,
    SCAN_DURATION_QUICK,
    SCORE_ZERO_ENTROPY,
    SCORE_LAZY_CLONE,
    SCORE_CALIBRATION_TAMPERING,
    SCORE_FLATLINE,
    SCORE_ODOMETER_ROLLBACK,
    SCORE_TIME_PARADOX,
    SCORE_THRESHOLD_SPOOFED,
)
from bg_state import state, state_lock, stop_scan
from bg_analysis import parse_ioreg, compute_health_score, compute_trends, format_operating_time
from bg_history import HistoryManager


def perform_scan(scan_mode="full"):
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
        state["scan_started"] = time.time()

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

        last_scan = HistoryManager.get_last_scan()

        # Populate metrics
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
                raw_hrs = data["TotalOperatingTime"]
                state["metrics"]["op_time"] = format_operating_time(raw_hrs)
                state["metrics"]["op_time_raw"] = raw_hrs
            if "Temperature" in data:
                temp_c = data["Temperature"] / 100
                state["metrics"]["temperature"] = f"{temp_c:.0f}°C"

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

        # Voltage stress test
        samples = []
        for i in range(duration):
            if stop_scan.is_set():
                with state_lock:
                    state["status"] = "complete"
                    state["verdict"] = "CANCELLED"
                    state["log"].append({
                        "title": "Scan Cancelled",
                        "desc": "User stopped the scan manually.",
                        "status": "warning",
                    })
                return
            pct = int(10 + ((i / duration) * 85))
            state["progress"] = pct
            s_res = subprocess.run(cmd, capture_output=True, text=True)
            m = re.search(r'"Voltage"\s*=\s*(\d+)', s_res.stdout)
            if m:
                samples.append(int(m.group(1)))
            time.sleep(1)

        # Forensic analysis
        state["progress"] = 100
        log = []
        score = 0
        cycles = data.get("CycleCount", 0)

        # Zero Entropy
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

        # Lazy Cloning
        if "Qmax" in data and "DesignCapacity" in data:
            if data["Qmax"][0] == data["DesignCapacity"] and cycles > 5:
                log.append({"title": "Firmware Hack: Lazy Cloning",
                    "desc": f"Qmax ({data['Qmax'][0]} mAh) matches Design Capacity exactly. Common hack to fake 100% health.",
                    "status": "fail"})
                score += SCORE_LAZY_CLONE

        # DOD0 Calibration
        if "DOD0" in data and "DesignCapacity" in data:
            if data["DOD0"][0] == data["DesignCapacity"]:
                log.append({"title": "Calibration Tampering: DOD0",
                    "desc": f"Depth of Discharge matches Capacity ({data['DesignCapacity']}). Impossible in genuine TI firmware.",
                    "status": "fail"})
                score += SCORE_CALIBRATION_TAMPERING

        # Permanent Failure
        if "PermanentFailureStatus" in data and data["PermanentFailureStatus"] != 0:
            log.append({"title": "Safety Alert: Permanent Failure",
                "desc": f"Critical failure flag: {hex(data['PermanentFailureStatus'])}. Battery unsafe.",
                "status": "fail"})

        # Voltage Flatline
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

        # Odometer Rollback
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

        log.append({"title": "Scan Saved", "desc": "Results logged to history.", "status": "success"})

        health_score = compute_health_score(data, score)
        trends = compute_trends(data, last_scan)
        
        HistoryManager.save_scan(res.stdout, data, health_score)

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

    with state_lock:
        state["status"] = "complete"
