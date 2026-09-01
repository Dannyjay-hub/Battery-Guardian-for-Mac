"""Battery Guardian scan orchestration.

Battery access and UI state live here. Forensic policy lives in
``bg_forensics.py`` and ``forensics/contract.json`` so it can be tested without
running IOKit or the web interface.
"""

from __future__ import annotations

import subprocess
import time

from bg_analysis import compute_health_score, compute_trends, format_operating_time, parse_ioreg
from bg_forensics import evaluate_battery
from bg_history import HistoryManager
from bg_state import state, state_lock, stop_scan


def perform_scan(scan_mode="full"):
    """Read one AppleSmartBattery snapshot and evaluate it safely."""
    with state_lock:
        if state["status"] == "running":
            return
        state.update({
            "status": "running",
            "progress": 0,
            "log": [],
            "score": 0,
            "health_score": 0,
            "verdict": "ANALYZING...",
            "scan_mode": scan_mode,
            "trends": {},
            "scan_started": time.time(),
            "policy_version": "--",
            "gauge_profile": "--",
            "evidence_complete": False,
            "missing_fields": [],
        })
    stop_scan.clear()

    try:
        state["progress"] = 20
        result = subprocess.run(
            ["ioreg", "-l", "-w0", "-r", "-c", "AppleSmartBattery"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError("Battery telemetry could not be read on this Mac.")
        if not result.stdout:
            raise RuntimeError("No built-in battery was detected.")

        data = parse_ioreg(result.stdout)
        last_scan = HistoryManager.get_last_scan()
        state["progress"] = 55
        _populate_metrics(data)

        evaluation = evaluate_battery(data)
        trends = compute_trends(data, last_scan)
        health_score = compute_health_score(data, evaluation.score)
        log = [
            {
                "title": item.title,
                "desc": item.description,
                "status": item.status,
                "check_id": item.check_id,
                "evidence_level": item.evidence_level,
                "score": item.score,
            }
            for item in evaluation.evidence
        ]
        log.append({
            "title": "Scan saved",
            "desc": f"Results were recorded with forensic policy {evaluation.policy_version}.",
            "status": "success",
            "check_id": "history",
            "evidence_level": "system",
            "score": 0,
        })

        state["progress"] = 90
        HistoryManager.save_scan(result.stdout, data, health_score)

        with state_lock:
            state.update({
                "progress": 100,
                "log": log,
                "score": evaluation.score,
                "health_score": health_score,
                "verdict": evaluation.verdict,
                "trends": trends,
                "policy_version": evaluation.policy_version,
                "gauge_profile": evaluation.profile or "unsupported",
                "evidence_complete": evaluation.complete,
                "missing_fields": list(evaluation.missing_fields),
            })
    except Exception as error:
        with state_lock:
            state.update({
                "progress": 100,
                "verdict": "ERROR",
                "score": 0,
                "health_score": 0,
                "evidence_complete": False,
                "log": [{
                    "title": "Scan error",
                    "desc": str(error),
                    "status": "fail",
                    "check_id": "scan_error",
                    "evidence_level": "system",
                    "score": 0,
                }],
            })
    finally:
        with state_lock:
            state["status"] = "complete"


def _populate_metrics(data):
    """Populate display-only metrics without drawing authenticity conclusions."""
    metrics = {
        "cycle_count": data.get("CycleCount", "--"),
        "write_count": data.get("DataFlashWriteCount", "--"),
        "qmax_var": "--",
        "op_time": "--",
        "op_time_raw": data.get("TotalOperatingTime", 0),
        "health": "N/A",
        "ratio": "--",
        "serial": data.get("Serial", "--"),
        "temperature": "--",
        "manufacture_date": "--",
    }

    qmax = data.get("Qmax")
    if isinstance(qmax, list) and qmax:
        metrics["qmax_var"] = max(qmax) - min(qmax)

    cycles = data.get("CycleCount")
    writes = data.get("DataFlashWriteCount")
    if isinstance(cycles, int) and isinstance(writes, int):
        metrics["ratio"] = round(writes / max(1, cycles), 1)

    operating_hours = data.get("TotalOperatingTime")
    if isinstance(operating_hours, (int, float)):
        metrics["op_time"] = format_operating_time(operating_hours)

    temperature = data.get("Temperature")
    if isinstance(temperature, (int, float)):
        metrics["temperature"] = f"{temperature / 10 - 273.15:.1f}°C"

    capacity = data.get("AppleRawMaxCapacity", data.get("MaxCapacity", 0))
    design = data.get("DesignCapacity", 0)
    if isinstance(capacity, int) and isinstance(design, int) and capacity > 0 and design > 0:
        metrics["health"] = f"{int(capacity / design * 100)}% ({capacity}/{design} mAh)"

    with state_lock:
        state["metrics"] = metrics
