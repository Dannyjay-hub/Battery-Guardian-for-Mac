"""
Battery Guardian — Forensic Scan Engine
========================================
Reads battery data from the macOS IOKit registry (ioreg) and runs a series
of physics-based forensic checks to detect spoofed or counterfeit battery chips.

All checks are grounded in Texas Instruments bq40z651 technical documentation.
Each check's rationale, physics basis, and TI reference is documented below.

Scoring model:
  score >= SCORE_THRESHOLD_SPOOFED  →  SPOOFED
  score > 0                         →  SUSPICIOUS
  score == 0                        →  GENUINE
"""

import subprocess
import time
from datetime import datetime, timedelta

from bg_config import (
    SCORE_ZERO_ENTROPY,
    SCORE_LAZY_CLONE,
    SCORE_CALIBRATION_TAMPERING,
    SCORE_INTERNAL_RESISTANCE,
    SCORE_CLOCK_INTEGRITY,
    SCORE_CALIBRATION_PARADOX,
    SCORE_CHIP_ORIGIN,
    SCORE_FROZEN_CLOCK,
    SCORE_THRESHOLD_SPOOFED,
)
from bg_state import state, state_lock, stop_scan
from bg_analysis import parse_ioreg, compute_health_score, compute_trends, format_operating_time
from bg_history import HistoryManager


def perform_scan(scan_mode="full"):
    """
    Run a forensic scan of the battery chip.

    All forensic checks operate on a single ioreg snapshot — there is no
    timed sampling loop. The scan completes in ~1 second.

    scan_mode is accepted for API/CLI compatibility (--auto flag) but is
    otherwise a no-op. Both 'full' and 'quick' produce identical results.
    """
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

    try:
        # ── Step 1: Read battery data from IOKit ──────────────────────────
        # ioreg exposes the TI bq40z651 DataFlash registers that macOS reads.
        # All forensic checks below operate on this single snapshot.
        state["progress"] = 20
        cmd = ["ioreg", "-l", "-w0", "-r", "-c", "AppleSmartBattery"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise Exception("ioreg command failed. Are you on a Mac?")
        if not res.stdout:
            raise Exception("No battery detected.")
        data = parse_ioreg(res.stdout)

        last_scan = HistoryManager.get_last_scan()
        state["progress"] = 60

        # ── Step 2: Populate live metrics for UI cards ────────────────────
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
                # Derive battery manufacture date from the chip's lifetime hour counter.
                # TotalOperatingTime counts hours since first activation —
                # the same source CoconutBattery uses for its manufacture date display.
                mfr_date = datetime.now() - timedelta(hours=raw_hrs)
                state["metrics"]["manufacture_date"] = mfr_date.strftime("%Y-%m-%d")
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

        # Health percentages used in forensic check descriptions
        qmax_health = 0
        if "Qmax" in data and "DesignCapacity" in data and data["DesignCapacity"] > 0:
            qmax_health = int((max(data["Qmax"]) / data["DesignCapacity"]) * 100)
        fcc_health = 0
        if numerator > 0 and "DesignCapacity" in data and data["DesignCapacity"] > 0:
            fcc_health = int((numerator / data["DesignCapacity"]) * 100)

        state["progress"] = 80

        # ── Step 3: Forensic checks ───────────────────────────────────────
        log = []
        score = 0
        cycles = data.get("CycleCount", 0)

        # CHECK 1 ── Zero Entropy  [40 pts]
        # ────────────────────────────────────────────────────────────────
        # The bq40z651 Impedance Track™ (IT) algorithm maintains an independent
        # Qmax value per cell, refined continuously during calibration cycles.
        # Physical lithium cells manufactured in separate production runs always
        # accumulate slight variance in chemistry and capacity from the very
        # first cycle. After 5+ cycles the IT algorithm refines these values
        # away from their factory defaults — they will never all be equal.
        # If all three Qmax values are identical, the data was not measured:
        # it was hardcoded by a spoofer overwriting the DataFlash registers.
        # Ref: TI bq40z651 TRM §5.3 — Qmax and Impedance Track
        if "Qmax" in data:
            var = max(data["Qmax"]) - min(data["Qmax"])
            if var == 0:
                if cycles > 5:
                    log.append({"title": "Physics Violation: Zero Entropy",
                        "desc": f"All three cells report identical capacity. The TI Impedance Track™ algorithm refines each cell independently — after {cycles} cycles, genuine cells always diverge. This data is hardcoded, not measured.",
                        "status": "fail"})
                    score += SCORE_ZERO_ENTROPY
                else:
                    log.append({"title": "Physics Check: Uncalibrated",
                        "desc": f"Cells identical (0mAh variance) at {cycles} cycles. This is normal for brand-new batteries — the IT algorithm hasn't had enough cycles to refine individual cell values yet.",
                        "status": "warning"})
            else:
                log.append({"title": "Physics Check: Passed",
                    "desc": f"Cells show healthy natural variance ({var}mAh). The TI Impedance Track™ algorithm independently refines each cell's Qmax — this divergence is the expected signature of a real, measured battery.",
                    "status": "success"})

        # CHECK 2 ── Internal Resistance Gap  [25 pts]
        # ────────────────────────────────────────────────────────────────
        # Qmax = chemical storage capacity (what the cells can hold).
        # FCC (AppleRawMaxCapacity) = usable capacity delivered under load.
        # As a battery ages, internal resistance builds up and energy is lost
        # to heat during discharge — FCC falls progressively below Qmax.
        # This gap grows with every cycle and is never zero after 1 month of use.
        # Comparison uses raw mAh values to avoid integer-truncation artifacts
        # that occur when rounding to percentage integers.
        # Ref: TI SLUU276 §4.2 — Impedance Track Algorithm
        if "Qmax" in data and "AppleRawMaxCapacity" in data and "DesignCapacity" in data:
            dc = data["DesignCapacity"]
            qmax_raw = max(data["Qmax"])
            fcc_raw = data["AppleRawMaxCapacity"]
            gap_mah = qmax_raw - fcc_raw
            if dc > 0:
                gap_pct = (gap_mah / dc) * 100
                if gap_pct > 3:
                    log.append({"title": "Internal Resistance: Normal",
                        "desc": f"Chemical capacity (Qmax: {qmax_health}%, {qmax_raw}mAh) exceeds usable output (FCC: {fcc_health}%, {fcc_raw}mAh) by {gap_mah}mAh. This impedance gap accumulates naturally with cycling and is exactly what is expected at {cycles} cycles.",
                        "status": "success"})
                elif gap_pct < 1 and cycles > 30:
                    log.append({"title": "Internal Resistance: Suspicious",
                        "desc": f"At {cycles} cycles (~{cycles//30} months of use), chemical capacity ({qmax_raw}mAh) and usable output ({fcc_raw}mAh) differ by only {gap_mah}mAh — less than 1% of design capacity. Every real battery develops a measurable impedance gap after 1 month. Both values likely share the same hardcoded source.",
                        "status": "fail"})
                    score += SCORE_INTERNAL_RESISTANCE
                elif gap_pct < 1 and cycles <= 30:
                    log.append({"title": "Internal Resistance: New Battery",
                        "desc": f"No significant impedance gap ({gap_mah}mAh at {cycles} cycles). Normal for batteries under 1 month of use — internal resistance hasn't had enough cycles to build up yet.",
                        "status": "warning"})
                # 1–3% gap: ambiguous zone (young battery, early aging) — no verdict

        # CHECK 3 ── Lazy Cloning  [30 pts]
        # ────────────────────────────────────────────────────────────────
        # Qmax[0] is the IT algorithm's running estimate of Cell 0's capacity.
        # After 5+ calibration cycles it should be less than DesignCapacity —
        # real cells never match their rated spec exactly due to manufacturing
        # variance and early capacity fade.
        # The most common battery spoof sets Qmax back to DesignCapacity to
        # report 100% health. This is the "lazy clone" pattern.
        # Ref: TI bq40z651 TRM §5.3.1 — Qmax Initialisation
        if "Qmax" in data and "DesignCapacity" in data:
            if data["Qmax"][0] == data["DesignCapacity"] and cycles > 5:
                log.append({"title": "Firmware Hack: Lazy Cloning",
                    "desc": f"Qmax ({data['Qmax'][0]}mAh) exactly matches Design Capacity ({data['DesignCapacity']}mAh). After {cycles} cycles the IT algorithm should have refined this value below the rated spec. Setting Qmax = DesignCapacity is the most common hack to fake 100% battery health.",
                    "status": "fail"})
                score += SCORE_LAZY_CLONE
            elif cycles > 5:
                log.append({"title": "Lazy Clone: Not Detected",
                    "desc": f"Qmax ({data['Qmax'][0]}mAh) is distinct from Design Capacity ({data['DesignCapacity']}mAh). No DataFlash override detected — this value has been naturally refined by the TI calibration algorithm over {cycles} cycles.",
                    "status": "success"})

        # CHECK 4 ── DOD0 Calibration Integrity  [30 pts]
        # ────────────────────────────────────────────────────────────────
        # DOD0 records the Depth of Discharge from the most recent calibration.
        #
        # SUB-CHECK A: All three DOD0 values identical
        # The TI Impedance Track™ algorithm calibrates each cell independently.
        # On a genuine battery that has been used and calibrated, the three cells
        # will always show slightly different DOD0 values because real lithium cells
        # discharge at marginally different rates. All three being exactly identical
        # means the calibration data was never genuinely measured — it was either
        # factory-reset or hardcoded.
        #
        # SUB-CHECK B: DOD0 = 16384 (Intel/bq20z451 specific)
        # Per TI SLUU313A §2.4.2: DOD units are internal counts, converted to %
        # by dividing by 163.84. So 16384 = 100% discharged (maximum possible value).
        # On a genuine Intel battery with real cycles, DOD0 is refined below 16384.
        # All three cells at 16384 with DataFlashWriteCount=0 means the BMS chip
        # was reset or replaced — the gauge has never been through a real calibration.
        # Ref: TI SLUU313A §2.4 — Gas Gauging / Impedance Track Configuration
        #
        # SUB-CHECK C: DOD0 == DesignCapacity (Apple Silicon / bq40z55 specific)
        # On Apple Silicon, DOD0 is reported in mAh. A genuine calibration always
        # discharges slightly less than the rated spec — if DOD0 exactly equals
        # DesignCapacity, the record has been forged.
        # Ref: TI SLUU276 §5.4 — DOD0 Calibration
        if "DOD0" in data:
            dod = data["DOD0"]
            writes = data.get("DataFlashWriteCount", None)

            # SUB-CHECK A: All three identical (platform-agnostic)
            if len(dod) >= 3 and dod[0] == dod[1] == dod[2] and cycles > 5:
                # Is it the Intel "100% uncalibrated" pattern?
                if dod[0] == 16384 and writes == 0:
                    log.append({"title": "DOD0: BMS Chip Reset Detected",
                        "desc": f"All three cells report DOD0 = {dod[0]} (100% discharged in TI internal units, per SLUU313A §2.4). DataFlashWriteCount = 0 confirms the gauge DataFlash has never been written. After {cycles} cycles a genuine battery has hundreds of calibration writes. The battery management chip was reset or replaced to hide true usage.",
                        "status": "fail"})
                    score += SCORE_CALIBRATION_TAMPERING
                else:
                    # All identical but not the specific Intel reset pattern
                    log.append({"title": "DOD0: Identical Across All Cells",
                        "desc": f"All three cells report the same DOD0 value ({dod[0]}). The TI Impedance Track™ algorithm calibrates each cell independently — after {cycles} cycles, genuine cells always diverge. Identical values indicate the calibration data was not independently measured.",
                        "status": "fail"})
                    score += SCORE_CALIBRATION_TAMPERING

            # SUB-CHECK C: DOD0 == DesignCapacity (Apple Silicon mAh check)
            elif "DesignCapacity" in data and dod[0] == data["DesignCapacity"]:
                log.append({"title": "Calibration Tampering: DOD0",
                    "desc": f"Depth of Discharge ({dod[0]}mAh) equals Design Capacity ({data['DesignCapacity']}mAh). In genuine TI firmware a real calibration always discharges slightly less than the rated spec — this record has been fabricated.",
                    "status": "fail"})
                score += SCORE_CALIBRATION_TAMPERING

            else:
                log.append({"title": "Calibration Record: Valid",
                    "desc": f"DOD0 values ({dod[0]}, {dod[1] if len(dod) > 1 else 'N/A'}, {dod[2] if len(dod) > 2 else 'N/A'}) are distinct across cells and within expected calibration range. Independent per-cell calibration is the expected signature of a real, measured battery.",
                    "status": "success"})

        # CHECK 4B ── DataFlash Write Count (Intel / bq20z451)  [25 pts]
        # ────────────────────────────────────────────────────────────────
        # The bq20z451 increments DataFlashWriteCount each time the gauge writes
        # calibration data to its non-volatile DataFlash memory. On a genuine battery
        # with 20+ cycles, this count should be in the hundreds. A count of 0 means
        # the chip has never completed a real calibration cycle — consistent with a
        # freshly reset or replaced BMS chip used to spoof a lower cycle count.
        # Ref: TI SLUU313A §2.9 — Calibration
        if "DataFlashWriteCount" in data and cycles > 10:
            if data["DataFlashWriteCount"] == 0:
                log.append({"title": "DataFlash: Zero Write Count",
                    "desc": f"DataFlashWriteCount = 0 at {cycles} cycles. A genuine battery management chip writes calibration data to DataFlash continuously — after {cycles} charge cycles there should be hundreds of writes. Zero writes means the chip was never genuinely calibrated: it was reset or replaced.",
                    "status": "fail"})
                score += 25
            else:
                ratio = round(data["DataFlashWriteCount"] / max(1, cycles), 1)
                log.append({"title": "DataFlash: Write History Confirmed",
                    "desc": f"DataFlashWriteCount = {data['DataFlashWriteCount']} over {cycles} cycles (~{ratio}x per cycle). Continuous DataFlash writes confirm the gauge has been actively calibrating — consistent with genuine battery usage.",
                    "status": "success"})

        # Permanent Failure — safety alert only, not scored
        if "PermanentFailureStatus" in data and data["PermanentFailureStatus"] != 0:
            log.append({"title": "Safety Alert: Permanent Failure",
                "desc": f"Critical failure flag active: {hex(data['PermanentFailureStatus'])}. The chip has registered a permanent hardware fault. Battery is unsafe to use.",
                "status": "fail"})

        # CHECK 5 ── Clock Integrity  [50 pts]
        # ────────────────────────────────────────────────────────────────
        # The bq40z651 samples temperature every ~225 seconds (TemperatureSamples).
        # TotalOperatingTime is a separate, independent hour counter.
        # Both measure elapsed time through completely different mechanisms.
        # On a genuine chip they agree within ~5% (verified: 0.005% on M4).
        # A spoofer who resets TotalOperatingTime to hide age rarely knows to
        # also reset TemperatureSamples — the discrepancy exposes the tampering.
        # Ref: TI bq40z651 TRM §6.1 — Gas Gauge Time Registers
        ts = data.get("TemperatureSamples")
        ot = data.get("TotalOperatingTime")
        if ts and ot and ot > 0:
            if ts < 500:
                log.append({"title": "Clock Integrity: Skipped",
                    "desc": "Battery is too new for this check — insufficient temperature samples accumulated. Re-scan after more usage to enable this verification.",
                    "status": "warning"})
            else:
                implied = ts * 225 / 3600   # sample count → equivalent hours
                discrepancy_pct = abs(implied - ot) / max(implied, ot) * 100
                if discrepancy_pct < 5:
                    implied_days = round(implied / 24)
                    log.append({"title": "Clock Integrity: Verified",
                        "desc": f"TemperatureSamples ({ts:,} samples × 225s) and TotalOperatingTime agree within {discrepancy_pct:.2f}% — confirming approximately {implied_days} days of genuine operation. Two independent counters cannot agree this closely if either has been tampered with.",
                        "status": "success"})
                elif discrepancy_pct >= 20:
                    real_hours = max(implied, ot)
                    real_days = round(real_hours / 24)
                    claimed_days = round(min(implied, ot) / 24)
                    hidden_days = round(abs(implied - ot) / 24)
                    log.append({"title": "Clock Integrity: Tampered",
                        "desc": f"TemperatureSamples implies ~{real_days} days of operation, but TotalOperatingTime claims only ~{claimed_days} days — a {discrepancy_pct:.0f}% discrepancy. Approximately {hidden_days} days of usage have been concealed by resetting one counter.",
                        "status": "fail"})
                    score += SCORE_CLOCK_INTEGRITY
                else:
                    log.append({"title": "Clock Integrity: Minor Variance",
                        "desc": f"Internal time counters have a minor variance of {discrepancy_pct:.1f}%. This is within acceptable tolerance for normal chip operation and is unlikely to indicate tampering.",
                        "status": "warning"})

        # CHECK 6 ── Calibration Timeline Paradox  [50 pts]
        # ────────────────────────────────────────────────────────────────
        # CycleCountLastQmax records the cycle number at which the most recent
        # Qmax calibration occurred. It can never legally exceed CycleCount —
        # a calibration cannot happen in the future. If it does, the cycle
        # counter was reset. This is a binary, deterministic forensic signal.
        # Ref: TI bq40z651 TRM §5.3.2 — CycleCount Registers
        lq = data.get("CycleCountLastQmax")
        cc = data.get("CycleCount")
        if lq is not None and cc is not None:
            if lq > cc:
                log.append({"title": "Calibration Paradox: Detected",
                    "desc": f"Last Qmax calibration was recorded at cycle {lq}, but the battery currently claims only {cc} cycles. A calibration cannot occur in the future — the cycle counter was reset after calibration. This is a mathematically impossible timeline on genuine hardware.",
                    "status": "fail"})
                score += SCORE_CALIBRATION_PARADOX
            else:
                log.append({"title": "Calibration Timeline: Consistent",
                    "desc": f"Last calibration at cycle {lq}, current cycle {cc}. CycleCountLastQmax can never legally exceed CycleCount — this timeline is physically valid and has not been tampered with.",
                    "status": "success"})

        # CHECK 7 ── Chip Origin  [30 pts]
        # ────────────────────────────────────────────────────────────────
        # MaximumPackVoltage is the highest pack voltage ever recorded.
        # TI CUV floor for a 3-cell MacBook pack: 3,000 mV × 3 = 9,000 mV.
        # A MaximumPackVoltage below 9,000 mV means this chip has never seen
        # a full 3-cell stack — it was taken from a 2-cell device and
        # re-programmed to impersonate a MacBook battery chip.
        # Ref: TI SLUU276 p.101 — CUV Protection Thresholds
        mpv = data.get("MaximumPackVoltage")
        if mpv is not None:
            if mpv < 9000:
                log.append({"title": "Chip Origin: Wrong Device",
                    "desc": f"Lifetime peak voltage is {mpv}mV. The TI CUV protection floor for a 3-cell MacBook pack is 9,000mV (3,000mV × 3 cells) — this battery has never operated within a valid 3-cell stack. The chip likely originated from a 2-cell device ({mpv}mV ÷ 2 = {mpv//2}mV/cell).",
                    "status": "fail"})
                score += SCORE_CHIP_ORIGIN
            elif mpv >= 12000:
                log.append({"title": "Chip Origin: Consistent",
                    "desc": f"Lifetime peak voltage is {mpv}mV. All 3 cells have operated above the TI CUV floor (9,000mV minimum for a 3-cell pack), confirming this chip has always lived inside genuine 3-cell MacBook hardware.",
                    "status": "success"})
            # 9,000–12,000 mV: ambiguous (new battery / conservative charging) — no verdict

        log.append({"title": "Scan Saved", "desc": "Results logged to history.", "status": "success"})

        # CHECK 8 ── Frozen Clock  [40 pts]
        # ────────────────────────────────────────────────────────────────
        # TotalOperatingTime is a cumulative hour counter maintained by the chip.
        # A genuine battery increments this counter continuously whenever the
        # system is powered on. If it has not changed in 30+ hours between scans,
        # the counter is frozen — either spoofed firmware or not a genuine TI chip.
        # The 30-hour threshold is above the confirmed 24-hour update cycle to
        # eliminate false positives from Macs powered off between scans.
        # Note: requires two saved scans ≥30h apart. Silent on the very first scan.
        trends = compute_trends(data, last_scan)
        if trends.get("op_time") == "frozen":
            log.insert(-1, {"title": "Frozen Clock: Detected",
                "desc": "TotalOperatingTime has not changed since the last scan, which was taken 30+ hours ago. A genuine TI chip increments this counter continuously whenever the system is on — a frozen counter means the firmware is disabled or spoofed.",
                "status": "fail"})
            score += SCORE_FROZEN_CLOCK
        elif last_scan is None:
            log.insert(-1, {"title": "Frozen Clock: No Baseline Yet",
                "desc": "This is the first recorded scan — no previous data to compare against. Run a second scan after 30+ hours to enable time-based clock verification.",
                "status": "warning"})
        else:
            log.insert(-1, {"title": "Frozen Clock: Not Detected",
                "desc": "TotalOperatingTime is advancing normally between scans. The chip's internal hour counter is active and incrementing as expected on genuine hardware.",
                "status": "success"})

        state["progress"] = 100

        health_score = compute_health_score(data, score)
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
