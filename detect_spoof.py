import sys
import re
import json
import statistics

def parse_ioreg_output(raw_text):
    """Parses the raw ioreg text into a dictionary of key characteristics."""
    data = {}
    
    # Extract Integers
    int_patterns = {
        "DesignCapacity": r'"DesignCapacity"\s*=\s*(\d+)',
        "CycleCount": r'"CycleCount"\s*=\s*(\d+)',
        "DataFlashWriteCount": r'"DataFlashWriteCount"\s*=\s*(\d+)',
        "AppleRawMaxCapacity": r'"AppleRawMaxCapacity"\s*=\s*(\d+)',
        "TotalOperatingTime": r'\"TotalOperatingTime\"\s*=\s*(\d+)',
    }
    
    for key, pattern in int_patterns.items():
        match = re.search(pattern, raw_text)
        if match:
            data[key] = int(match.group(1))
            
    # Extract Arrays (Cell Data)
    array_patterns = {
        "Qmax": r'"Qmax"\s*=\s*\((\d+),(\d+),(\d+)\)',
        "DOD0": r'"DOD0"\s*=\s*\((\d+),(\d+),(\d+)\)',
        "CellVoltage": r'"CellVoltage"\s*=\s*\((\d+),(\d+),(\d+)\)'
    }
    
    for key, pattern in array_patterns.items():
        match = re.search(pattern, raw_text)
        if match:
            data[key] = [int(match.group(1)), int(match.group(2)), int(match.group(3))]
            
    return data

def analyze_battery(data):
    """Performs forensic analysis on the parsed battery data."""
    results = {
        "Verdict": "UNKNOWN",
        "Confidence": 0,
        "Anomalies": [],
        "Physics_Checks": {}
    }
    
    if "Qmax" not in data or "DesignCapacity" not in data:
        results["Anomalies"].append("MISSING_CRITICAL_DATA: Qmax or DesignCapacity not found.")
        return results

    # 1. The Entropy Check (Qmax Variance)
    # Real cells vary. Spoofed cells are identical.
    qmax_variance = max(data["Qmax"]) - min(data["Qmax"])
    qmax_std_dev = statistics.stdev(data["Qmax"])
    
    results["Physics_Checks"]["Entropy_Score"] = qmax_variance
    
    if qmax_variance == 0:
        results["Anomalies"].append("ZERO_ENTROPY: All Qmax cells are identical (Physics Violation).")
        results["Confidence"] += 40
        
    # 2. The Lazy Copy Check (DesignCapacity Cloning)
    # Spoofer often copies DesignCapacity into Qmax to force 100% health
    if data["Qmax"][0] == data["DesignCapacity"]:
        results["Anomalies"].append(f"LAZY_CLONE: Qmax mismatch. Chip values ({data['Qmax'][0]}) identical to Design Capacity ({data['DesignCapacity']}).")
        results["Confidence"] += 30

    # 3. The DOD0 Anomaly (The Smoking Gun)
    # DOD0 is a calibration offset, NEVER equal to DesignCapacity in real TI Chips
    if "DOD0" in data:
        if data["DOD0"][0] == data["DesignCapacity"]:
             results["Anomalies"].append(f"FIRMWARE_HACK: DOD0 calibration ({data['DOD0'][0]}) matches Design Capacity. This is impossible in genuine firmware.")
             results["Confidence"] += 30
    
    # 4. The Odometer Check (Write Count Ratio)
    if "DataFlashWriteCount" in data and "CycleCount" in data:
        cycle_count = max(data["CycleCount"], 1) # Avoid div/0
        ratio = data["DataFlashWriteCount"] / cycle_count
        
        results["Physics_Checks"]["Write_Ratio"] = round(ratio, 2)
        
        if ratio > 50 and cycle_count < 20: 
             results["Anomalies"].append(f"ODOMETER_ROLLBACK: Massive write count ({data['DataFlashWriteCount']}) for low cycle count ({cycle_count}). Chip is reused.")
             results["Confidence"] += 20

    # 5. The Time Paradox (Operating Time vs. Writes)
    # Real batteries run for thousands of hours. Spoofed ones might be frozen at low values.
    # Logic: If WriteCount is HUGE (>5000) but OperatingTime is LOW (<500 hours), it's a "Time Freeze" or "Rollback".
    if "TotalOperatingTime" in data and "DataFlashWriteCount" in data:
        op_time_hours = data["TotalOperatingTime"]
        # Convert operating time (usually minutes or 2s intervals, but let's assume raw value for ratio)
        # Note: older Macs use minutes, newer might vary. We look for the RATIO.
        # A real battery has lots of time for lots of writes.
        if data["DataFlashWriteCount"] > 1000 and op_time_hours < 500:
             results["Anomalies"].append(f"TIME_PARADOX: High write count ({data['DataFlashWriteCount']}) but suspiciously low Operating Time ({op_time_hours}). Possible Frozen Clock.")
             results["Confidence"] += 15

    # 6. The Qmax Time Freeze (TI Datasheet Proof)
    # Qmax ONLY updates after 2-5 hours of relaxation.
    # If CycleCount > 10 but Qmax == DesignCapacity, it means the chip was reset and NEVER rested.
    if "Qmax" in data:
        # Check if the first cell matches DesignCapacity exactly
        if data["Qmax"][0] == data["DesignCapacity"] and data.get("CycleCount", 0) > 10:
             results["Anomalies"].append(f"QMAX_TIME_FREEZE: Qmax ({data['Qmax'][0]}) equals Design Capacity on a used battery ({data.get('CycleCount',0)} cycles). Chip was reset and never learned.")
             results["Confidence"] += 50

    # 7. Permanent Failure (PF) Decoder
    # Hex flags indicating why the battery died.
    # Source: TI SLUU276, Subclass 96
    pf_flags = {
        0x01: "Safety Overvoltage [SOV]",
        0x02: "Safety Overcharge [SOC]",
        0x04: "Cell Undervoltage [CUV]",
        0x10: "Cell Imbalance [CIM]",
        0x20: "FET Failure [FET]",
        0x80: "AFE Communication Error [AFE]"
    }
    
    # Check for "PermanentFailureStatus" (if present in ioreg)
    pf_status = 0
    # Try multiple common keys for PF Status
    if "PermanentFailureStatus" in data: pf_status = data["PermanentFailureStatus"]
    elif "PFStatus" in data: pf_status = data["PFStatus"]
        
    if pf_status > 0:
        reasons = []
        for flag, desc in pf_flags.items():
            if pf_status & flag:
                reasons.append(desc)
        results["Anomalies"].append(f"PERMANENT_FAILURE_FLAG: Battery has tripped safety kill-switch. Code: {hex(pf_status)} -> {', '.join(reasons)}")
        results["Confidence"] += 100 # This is a dead battery for sure.

    # Final Verdict
    if results["Confidence"] >= 80:
        results["Verdict"] = "SPOOFED / TAMPERED"
    elif results["Confidence"] >= 40:
        results["Verdict"] = "HIGHLY SUSPICIOUS"
    else:
        results["Verdict"] = "GENUINE"
    
    # Add Manual Check Prompts
    if results["Confidence"] > 0:
        results["Anomalies"].append("\n--- MANUAL CHECKS REQUIRED ---")
        results["Anomalies"].append("1. TIME FREEZE: Check 'TotalOperatingTime' tomorrow. If it is still exact same number, it is SPOOFED.")
        results["Anomalies"].append("2. FLATLINE TEST: Run 'ioreg -l' in a loop for 60s. If Voltage is identical for 20+ samples, it is SPOOFED.")
        results["Anomalies"].append("3. LIFETIME DATA: Look for 'LifeTime Data' or 'Subclass 59' in logs. If MaxTemp is 1400 (Celsius) or MaxVolt is 3500 (mV), it is virgin/fake.")
        
    return results

def main():
    print("--- Mac Battery Forensic Tool v1.0 ---\n")
    print("Paste your 'ioreg -l -w0 -r -c AppleSmartBattery' output below.")
    print("Press Ctrl+D (or Ctrl+Z on Windows) when finished:\n")
    
    try:
        raw_input = sys.stdin.read()
    except KeyboardInterrupt:
        return

    print("\n\n--- ANALYZING ---\n")
    
    data = parse_ioreg_output(raw_input)
    if not data:
        print("Error: Could not parse battery data. Make sure you pasted the full ioreg output.")
        return

    report = analyze_battery(data)
    
    print(f"VERDICT: {report['Verdict']}")
    print(f"Confidence Score: {report['Confidence']}%")
    print("-" * 30)
    print("EVIDENCE FOUND:")
    for anomaly in report["Anomalies"]:
        print(f"  [!] {anomaly}")
        
    print("-" * 30)
    print("PHYSICS METRICS:")
    print(f"  Entropy (Variance): {report['Physics_Checks'].get('Entropy_Score', 'N/A')} (Should be > 0)")
    print(f"  Write Ratio: {report['Physics_Checks'].get('Write_Ratio', 'N/A')} (Normal is ~5.0)")

if __name__ == "__main__":
    main()
