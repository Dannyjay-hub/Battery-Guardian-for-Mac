"""
Battery Guardian — Pure Analysis Functions
==========================================
Stateless utility functions for parsing ioreg output, computing health scores,
computing scan-to-scan trends, and formatting display values.

No I/O, no state, no side-effects. Every function here is a pure transformation:
given the same inputs it always produces the same output. This makes the module
easy to unit test and safe to call from any thread.

Key functions
─────────────
  parse_ioreg()        — Convert raw ioreg stdout to a typed dict of registers
  compute_health_score() — Produce a 0-100 composite health/spoof score
  compute_trends()     — Compare current snapshot to previous scan for trend arrows
  format_operating_time() — Convert raw hours to "N years, M months, D days"
"""

import re
from datetime import datetime


def format_operating_time(hours):
    """
    Convert a raw TotalOperatingTime hour count to a human-readable string.

    TotalOperatingTime is stored as an integer count of hours by the TI chip.
    Breaks it down into years / months / days for display in the UI.

    Args:
        hours: Raw hour count from the TI register (int or float).

    Returns:
        Formatted string, e.g. "3 years, 7 months, 13 days".
        Returns "--" for invalid or zero values.
    """
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
    """
    Parse the stdout of `ioreg -l -w0 -r -c AppleSmartBattery` into a typed dict.

    ioreg returns a human-readable property list. This function extracts:
      - Integer registers (e.g. "CycleCount" = 129)
      - String registers (e.g. "Serial" = "F5D8...")
      - Array registers (e.g. "Qmax" = (4370, 4350, 4362))

    Array fields tracked (TI DataFlash per-cell arrays):
      Qmax         — Per-cell chemical capacity (mAh), refreshed by IT algorithm
      CellVoltage  — Per-cell real-time voltage (mV)
      DOD0         — Per-cell depth of discharge at last calibration (mAh)
      WeightedRa   — Per-cell internal resistance (mΩ), IT algorithm output
      PresentDOD   — Per-cell current depth of discharge (mAh)

    Args:
        text: Raw stdout string from the ioreg command.

    Returns:
        Dict mapping register names to int, str, or list[int] values.
    """
    data = {}

    # Integer registers: "RegisterName" = 12345
    for m in re.finditer(r'"(\w+)"\s*=\s*(\d+)', text):
        data[m.group(1)] = int(m.group(2))

    # String registers: "RegisterName" = "value" (only if not already int)
    for m in re.finditer(r'"(\w+)"\s*=\s*"([^"]+)"', text):
        if m.group(1) not in data:
            data[m.group(1)] = m.group(2)

    # Array registers: "RegisterName" = (v1, v2, v3)
    for key in ["Qmax", "CellVoltage", "DOD0", "WeightedRa", "PresentDOD"]:
        m = re.search(rf'"{key}"\s*=\s*\(([^)]+)\)', text)
        if m:
            vals = [int(x.strip()) for x in m.group(1).split(",") if x.strip().isdigit()]
            if vals:
                data[key] = vals

    return data


def compute_health_score(data, scan_score):
    """
    Compute a composite 0–100 health score for display in the ring chart.

    The score combines forensic penalty (from failed checks) with physical
    battery condition (capacity fade, cycle aging). It is not the same as
    raw battery health percentage — it reflects both authenticity and condition.

    Scoring logic:
      Base:        100 points (perfect genuine battery)
      Spoof penalty: subtract up to 80 pts for failed forensic checks
      Capacity fade: subtract proportionally if health% < 80%
      Cycle aging:   subtract up to 15 pts for very high cycle counts (>1000)

    Args:
        data:       Parsed ioreg dict (from parse_ioreg).
        scan_score: Accumulated forensic penalty from bg_scanner checks.

    Returns:
        Integer in range [0, 100].
    """
    score = 100

    # Forensic penalty — capped at 80 to leave room for physical degradation signal
    score -= min(scan_score, 80)

    # Capacity fade penalty — linear below 80% health
    if "AppleRawMaxCapacity" in data and "DesignCapacity" in data:
        cap = data["AppleRawMaxCapacity"]
        design = data["DesignCapacity"]
        if design > 0:
            health_pct = (cap / design) * 100
            if health_pct < 80:
                score -= int((80 - health_pct) * 0.5)

    # Cycle aging penalty — only relevant at very high cycle counts
    cycles = data.get("CycleCount", 0)
    if cycles > 1000:
        score -= min(int((cycles - 1000) / 50), 15)
    elif cycles > 500:
        score -= min(int((cycles - 500) / 100), 5)

    return max(0, min(100, score))


def compute_trends(current_data, last_entry):
    """
    Compare the current scan snapshot to the last saved scan entry.

    Used to generate trend arrows (↑ / ↓ / → / ⏸) in the UI metric cards
    and to detect the Frozen Clock condition in Check 8.

    Frozen Clock logic:
      If TotalOperatingTime is unchanged AND the last scan was taken 30+ hours
      ago, the counter is considered frozen. The 30-hour threshold is above the
      chip's confirmed 24-hour update interval to avoid false positives from
      Macs that were off between scans.

    Args:
        current_data: Parsed ioreg dict from the current scan.
        last_entry:   Dict from HistoryManager.get_last_scan(), or None if
                      no previous scan exists.

    Returns:
        Dict with keys: "cycles", "health", "op_time"
        Values: "up" | "down" | "stable" | "frozen"
        Missing keys mean the data was unavailable for comparison.
    """
    trends = {}
    if not last_entry or "parsed" not in last_entry:
        return trends

    prev = last_entry["parsed"]

    # Cycle count trend (always increases on genuine hardware)
    curr_cycles = current_data.get("CycleCount", 0)
    prev_cycles = prev.get("CycleCount", 0)
    if curr_cycles > prev_cycles:
        trends["cycles"] = "up"
    elif curr_cycles == prev_cycles:
        trends["cycles"] = "stable"

    # Battery health trend (capacity fade — should trend down over time)
    curr_max = current_data.get("AppleRawMaxCapacity", 0)
    prev_max = prev.get("AppleRawMaxCapacity", 0)
    if curr_max > 0 and prev_max > 0:
        if curr_max < prev_max:
            trends["health"] = "down"
        elif curr_max > prev_max:
            trends["health"] = "up"
        else:
            trends["health"] = "stable"

    # TotalOperatingTime trend — used for Frozen Clock detection
    curr_op = current_data.get("TotalOperatingTime", 0)
    prev_op = prev.get("TotalOperatingTime", 0)
    if curr_op > prev_op:
        trends["op_time"] = "up"
    elif curr_op == prev_op:
        try:
            prev_time = datetime.fromisoformat(last_entry.get("timestamp", ""))
            if (datetime.now() - prev_time).total_seconds() > 108000:  # 30 hours
                trends["op_time"] = "frozen"
            else:
                trends["op_time"] = "stable"
        except Exception:
            trends["op_time"] = "stable"

    return trends
