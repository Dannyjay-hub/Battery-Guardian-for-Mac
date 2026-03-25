"""Battery Guardian — pure analysis functions (no I/O, no state)."""

import re
from datetime import datetime

from bg_config import (
    SCORE_ZERO_ENTROPY,
    SCORE_LAZY_CLONE,
    SCORE_CALIBRATION_TAMPERING,
    SCORE_FLATLINE,
    SCORE_ODOMETER_ROLLBACK,
    SCORE_TIME_PARADOX,
)


def format_operating_time(hours):
    """Convert raw hours to human-readable format."""
    if not isinstance(hours, (int, float)) or hours <= 0:
        return "--"

    parts = []
    years = int(hours // 8760)
    rem = hours % 8760
    months = int(rem // 730)
    rem = rem % 730
    days = int(rem // 24)

    if years > 0:
        parts.append(f"{years} year{'s' if years > 1 else ''}")
    if months > 0:
        parts.append(f"{months} month{'s' if months > 1 else ''}")
    if days > 0:
        parts.append(f"{days} day{'s' if days > 1 else ''}")

    return ", ".join(parts) if parts else f"{int(hours)} hours"


def parse_ioreg(text):
    """Parse ioreg output into a dict of battery values."""
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

    score -= min(scan_score, 80)

    if "AppleRawMaxCapacity" in data and "DesignCapacity" in data:
        cap = data["AppleRawMaxCapacity"]
        design = data["DesignCapacity"]
        if design > 0:
            health_pct = (cap / design) * 100
            if health_pct < 80:
                score -= int((80 - health_pct) * 0.5)

    cycles = data.get("CycleCount", 0)
    if cycles > 1000:
        score -= min(int((cycles - 1000) / 50), 15)
    elif cycles > 500:
        score -= min(int((cycles - 500) / 100), 5)

    return max(0, min(100, score))


def compute_trends(current_data, last_entry):
    """Compare current scan vs last scan. Returns dict of trend strings."""
    trends = {}
    if not last_entry or "parsed" not in last_entry:
        return trends

    prev = last_entry["parsed"]

    curr_cycles = current_data.get("CycleCount", 0)
    prev_cycles = prev.get("CycleCount", 0)
    if curr_cycles > prev_cycles:
        trends["cycles"] = "up"
    elif curr_cycles == prev_cycles:
        trends["cycles"] = "stable"

    curr_max = current_data.get("AppleRawMaxCapacity", 0)
    prev_max = prev.get("AppleRawMaxCapacity", 0)
    if curr_max > 0 and prev_max > 0:
        if curr_max < prev_max:
            trends["health"] = "down"
        elif curr_max > prev_max:
            trends["health"] = "up"
        else:
            trends["health"] = "stable"

    curr_op = current_data.get("TotalOperatingTime", 0)
    prev_op = prev.get("TotalOperatingTime", 0)
    if curr_op > prev_op:
        trends["op_time"] = "up"
    elif curr_op == prev_op:
        try:
            prev_time = datetime.fromisoformat(last_entry.get("timestamp", ""))
            if (datetime.now() - prev_time).total_seconds() > 86400:
                trends["op_time"] = "frozen"
            else:
                trends["op_time"] = "stable"
        except Exception:
            trends["op_time"] = "stable"

    return trends
