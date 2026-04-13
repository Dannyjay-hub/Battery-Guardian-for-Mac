# Battery Guardian

**A macOS battery forensics tool that detects counterfeit, reprogrammed, and spoofed MacBook batteries.**

Battery Guardian reads directly from the Texas Instruments Smart Battery System (SBS) gas gauge chip inside your battery — the same registers Apple's own diagnostics use — and applies 8 independent physics-based forensic checks to determine whether your battery is genuine or faked.

No heuristics. No guessing. Pure chip-level forensics.

---

## Why This Exists

The MacBook battery replacement market is flooded with counterfeit and reprogrammed chips. These batteries:
- Report 100% health regardless of actual cell condition
- Show falsified cycle counts
- Clone another battery's serial number
- Silently degrade without warning

Existing tools (CoconutBattery, iStatMenus, system profiler) only read and display the data the chip reports. They have no way to tell you if that data is real.

Battery Guardian doesn't just read the data — it **audits it** using invariants from the TI firmware specification that a spoofed chip cannot fake without contradicting itself.

---

## Features

- **8 independent forensic checks** — each grounded in Texas Instruments SBS battery management IC specifications
- **Instant results** — single `ioreg` snapshot, no waiting
- **Physics-based scoring** — weighted penalty system with documented thresholds
- **Monthly history trends** — track health and cycles over time automatically
- **Battery manufacture date** — derived from the chip's internal hour counter
- **Expandable detailed scan log** — per-entry history with full metrics
- **Scheduled headless scanning** — macOS LaunchAgent automation
- **Shareable forensic report** — plain-text export for clipboard sharing
- **Zero dependencies at runtime** — uses only native macOS `ioreg`

---

## How It Works

### The TI Smart Battery System (SBS) Chip

MacBook batteries contain a **Texas Instruments Smart Battery System (SBS) gas gauge IC** — commonly from TI's bq40z series (e.g. bq40z651, bq40z50, bq40z55), depending on the MacBook generation. This chip:
- Runs the **Impedance Track™ (IT) algorithm** — a proprietary cell modelling algorithm that continuously measures and refines individual cell capacity (Qmax)
- Maintains a **DataFlash** memory containing calibration history, cycle counts, time counters, and per-cell measurements
- Exposes all of this via **SMBus** to the host, which macOS reads through IOKit and surfaces via `ioreg`

Battery Guardian's forensic checks are grounded in the Impedance Track™ specification and DataFlash register structure, which are consistent across TI's SBS-compliant chip family. The checks have been validated against real hardware across multiple MacBook generations.

Data is read using:
```bash
ioreg -l -w0 -r -c AppleSmartBattery
```

### The 8 Forensic Checks

Each check is validated against Texas Instruments documentation. Every check passes silently on your genuine M1 MacBook (verified: 0.005% discrepancy on real hardware).

---

#### CHECK 1 — Physics Check: Zero Entropy `[40 pts]`

**What it checks:** Whether all three cell Qmax values are identical.

**The physics:** The IT algorithm refines each cell's Qmax independently. Lithium cells manufactured separately always diverge in capacity due to microscopic chemistry differences. After 5+ cycles, genuine cells show measurable variance. If all three are identical, the values are hardcoded.

**Reference:** TI bq40z651 TRM §5.3 — Qmax and Impedance Track™

---

#### CHECK 2 — Internal Resistance Gap `[25 pts]`

**What it checks:** Whether the gap between chemical capacity (Qmax) and usable capacity (FCC) is suspiciously small.

**The physics:** As a battery ages, internal resistance builds up. Energy is lost to heat during discharge — Full Charge Capacity (FCC) falls progressively below Qmax. This gap grows with every cycle. After 30+ cycles (~1 month), it is never less than ~1% of design capacity on genuine hardware. Raw mAh values are compared (not rounded percentages) to avoid integer-truncation artifacts.

**Reference:** TI SLUU276 §4.2 — Impedance Track™ Algorithm

---

#### CHECK 3 — Lazy Cloning `[30 pts]`

**What it checks:** Whether Qmax[0] exactly matches DesignCapacity.

**The physics:** The most common battery spoof sets Qmax = DesignCapacity to always report 100% health. After 5+ calibration cycles, Qmax should be refined below the rated spec. An exact match is the "lazy clone" signature.

**Reference:** TI bq40z651 TRM §5.3.1 — Qmax Initialisation

---

#### CHECK 4 — DOD0 Calibration Tampering `[30 pts]`

**What it checks:** Whether the Depth of Discharge calibration record equals DesignCapacity.

**The physics:** DOD0 records how many mAh were extracted during the most recent full calibration run. No real cell ever delivers exactly its rated capacity — the value is always slightly less. A DOD0 equal to DesignCapacity is fabricated. This catches spoofed batteries that patch the Qmax registers but forget to sanitise the calibration subsystem.

**Reference:** TI SLUU276 §5.4 — DOD0 Calibration

---

#### CHECK 5 — Clock Integrity `[50 pts]`

**What it checks:** Whether two independent time counters agree.

**The physics:** The chip samples temperature every ~225 seconds (`TemperatureSamples`) and separately maintains `TotalOperatingTime` in hours. Both measure elapsed time using completely independent mechanisms. On genuine hardware they agree within ~5% (measured: 0.005% on M4 MacBook Pro, 2025). A spoofer who resets `TotalOperatingTime` to hide age rarely knows to also reset `TemperatureSamples`. The cross-counter discrepancy exposes the tampering.

**Reference:** TI bq40z651 TRM §6.1 — Gas Gauge Time Registers

---

#### CHECK 6 — Calibration Timeline Paradox `[50 pts]`

**What it checks:** Whether `CycleCountLastQmax` > `CycleCount`.

**The physics:** `CycleCountLastQmax` records the cycle number at which the most recent Qmax calibration occurred. It can never legally exceed `CycleCount` — a calibration cannot happen in the future. If it does, the cycle counter was reset after a calibration event. This is a binary, deterministic signal: either physically valid or mathematically impossible.

**Reference:** TI bq40z651 TRM §5.3.2 — CycleCount Registers

---

#### CHECK 7 — Chip Origin `[30 pts]`

**What it checks:** Whether `MaximumPackVoltage` is consistent with a 3-cell battery.

**The physics:** `MaximumPackVoltage` is the highest pack voltage ever recorded in the chip's lifetime. The TI Cell Under Voltage (CUV) protection floor is 3,000 mV/cell. For a genuine 3-cell MacBook pack: minimum = 3,000 × 3 = **9,000 mV**. A value below 9,000 mV means the chip has never operated inside a 3-cell stack — it came from a 2-cell device (phone/tablet).

**Reference:** TI SLUU276 p.101 — CUV Protection Thresholds

---

#### CHECK 8 — Frozen Clock `[40 pts]`

**What it checks:** Whether `TotalOperatingTime` has advanced since the last saved scan.

**The physics:** `TotalOperatingTime` is a cumulative hour counter. A genuine chip increments it continuously whenever the system is on. If it hasn't changed in 30+ hours between two scans, the counter is frozen — either the firmware is spoofed or the chip is not a genuine TI gauge. The 30-hour threshold (above the confirmed 24-hour chip update cycle) eliminates false positives from powered-off Macs.

**Note:** Requires two scans taken 30+ hours apart. Silent on the first scan.

---

### Scoring Model

Each failed check adds a weighted penalty to the total score:

| Check | Points |
|-------|--------|
| Clock Integrity | 50 |
| Calibration Paradox | 50 |
| Zero Entropy | 40 |
| Frozen Clock | 40 |
| Lazy Cloning | 30 |
| DOD0 Tampering | 30 |
| Chip Origin | 30 |
| Internal Resistance | 25 |

**Verdict thresholds:**
- `score ≥ 40` → **SPOOFED**
- `score > 0` → **SUSPICIOUS**
- `score = 0` → **GENUINE**

A single high-confidence check (≥ 40 pts) is sufficient for a SPOOFED verdict.

---

## Requirements

**Current release:**
- macOS 10.14 Mojave or later
- MacBook with a built-in battery (not compatible with Mac Mini, iMac, Mac Pro, Mac Studio)
- Python 3.9+ (for running from source only)

**Planned platform support:**
- 📱 iPhone / iPad battery forensics
- 💻 Windows laptop battery support

---

## Install (Pre-built)

1. Download `BatteryGuardian_v1.3.2.dmg` from [Releases](https://github.com/Dannyjay-hub/Battery-Guardian-for-Mac/releases)
2. Open the DMG and drag **Battery Guardian** to the Applications folder
3. Open **ReadMeFirst.html** inside the DMG for first-launch instructions

> **Gatekeeper:** The app is not notarized. On first launch, right-click → Open instead of double-clicking. If macOS says "cannot be verified", click Cancel — do not move to Trash — then right-click and Open.

---

## Run from Source

```bash
# Clone the repository
git clone https://github.com/Dannyjay-hub/Battery-Guardian-for-Mac.git
cd Battery-Guardian-for-Mac

# Install dependencies
pip3 install pywebview

# Run
python3 battery_guardian_web.py
```

The app opens as a native macOS window. Results load automatically on launch.

---

## Headless / Automation Mode

Battery Guardian supports background scanning via macOS LaunchAgent:

```bash
# Schedule daily scans at 20:00 for 30 days
python3 battery_guardian_web.py --enable-automation 30

# Run a single headless scan (used by LaunchAgent)
python3 battery_guardian_web.py --auto

# Open in browser instead of native window
python3 battery_guardian_web.py --no-window
```

Scan history is saved to `~/.battery_guardian_log.json`.

---

## Build from Source

Requires `pyinstaller`:

```bash
pip3 install pyinstaller
bash build_release.sh
```

Output: `BatteryGuardian_v1.3.2.dmg` — a self-contained macOS `.app` bundle packaged as a DMG installer.

---

## Project Structure

```
Battery Guardian/
├── battery_guardian_web.py   # Entry point — server, CLI, window management
├── bg_scanner.py             # Core forensic engine — all 8 checks
├── bg_analysis.py            # Pure analysis functions (parsing, scoring, trends)
├── bg_automation.py          # LaunchAgent installer and share report generator
├── bg_config.py              # Scoring constants and configuration
├── bg_state.py               # Shared mutable scan state (thread-safe)
├── bg_history.py             # Per-scan history persistence (JSON)
├── bg_platform.py            # Platform detection and Mac model identification
├── bg_server.py              # HTTP request handler for the web UI
├── bg_template.html          # Frontend UI (HTML/CSS/JS)
├── bg_guide.html             # Forensic methodology guide page
├── ReadMeFirst.html          # DMG install guide (bundled in installer)
├── dmg_background.png        # DMG window background
└── build_release.sh          # PyInstaller + DMG build script
```

---

## How to Contribute

Battery Guardian is open source and contributions are welcome. Areas where help would be great:

- **Expanding the forensic engine** — additional DataFlash register checks
- **iPhone/iPad support** — extending forensics to Apple mobile batteries
- **Swift/native rewrite** — future direction for Mac App Store distribution
- **Test cases** — documented examples of spoofed battery register dumps (anonymised)

Please open an issue before submitting a significant PR.

---

## Technical References

All forensic checks are grounded in the following publicly available Texas Instruments documentation:

| Document | Description |
|----------|-------------|
| [bq40z651 Technical Reference Manual](https://www.ti.com/product/BQ40Z651) | Primary register reference — Qmax, CycleCount, TemperatureSamples, TotalOperatingTime |
| [SLUU276 — Impedance Track Technology](https://www.ti.com/lit/an/slua450a/slua450a.pdf) | IT algorithm — DOD0, FCC, internal resistance model |
| [SLUA908 — Battery Authentication](https://www.ti.com/lit/an/slua908/slua908.pdf) | DataFlash write patterns and authentication design |

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

## Author

Built by [@Dannyjay-hub](https://github.com/Dannyjay-hub) — Battery Guardian for Mac.

*If this tool helped you identify a fake battery, consider starring the repo. It helps others find it.*
