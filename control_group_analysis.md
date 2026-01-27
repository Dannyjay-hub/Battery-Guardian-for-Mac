# Control Group Analysis: Ebuka's Battery
**Date:** 2026-01-27
**Subject:** Control Group Data (Ebuka - MacBook Pro)
**Duration:** 5 Days (Jan 22 - Jan 27)

## Executive Summary
The control group data (Ebuka's battery) exhibits **healthy, natural behavior**, providing a crucial baseline to contrast with the Suspect Battery. Key indicators confirm it is a genuine, chemically active cell with a functioning gas gauge.

## 1. Voltage Analysis (The "Heartbeat")
- **Method:** `detect_flatlines` (Voltage Hard-Lock Check)
- **Result:** Max Voltage Lock Streak: **1 sample**
- **Meaning:** The voltage fluctuates with *every single reading*. 
- **Conclusion:** **NORMAL / ORGANIC**. 
    - Real batteries are "noisy"; voltage constantly jitters due to tiny load changes and chemical reactions.
    - A spoofed/emulator chip often outputs a perfect, unmoving voltage (e.g., "11500mV" for 30 minutes straight) because it's just a constant value programmed in a table. Ebuka's battery is "alive".

## 2. Operating Time (The "Clock")
- **Method:** `detect_time_paradox` (TotalOperatingTime Check)
- **Result:** 
    - Real Time Elapsed: ~5.5 Days
    - Battery Counter Increase: **120 units**
    - **Pattern Observed:** The counter adds exactly **24 units** once per day (around 7-9 PM).
- **Meaning:** The battery's internal life-meter is **running** and has a specific update heartbeat.
    - **Discovery:** Healthy Apple batteries (or at least this TI controller generation) appear to batch-update `TotalOperatingTime` in 24-hour increments rather than continuously ticking.
    - **Forensic Marker:** We look for these "step jumps". A counterfeit chip often shows a perfectly flat line (zero change) forever. Ebuka's battery shows the "Heartbeat of Life".

## 3. Data Integrity
- **Log Count:** 15 robust samples.
- **Cycle Count:** Increased from 1018 to 1019 over the period.
- **Consistency:** No corruption or impossible jumps in data.

## Verdict: GENUINE BASELINE ESTABLISHED
This data confirms what "Good" looks like:
1.  **Noisy Voltage** (Never stays the same).
2.  **Moving Clock** (OperatingTime increases).
3.  **Logical Aging** (Cycles and capacity change gradually).

We can now confidently use these patterns to impeach the Suspect Battery if it shows "Flatline Voltage" or a "Frozen Clock".
