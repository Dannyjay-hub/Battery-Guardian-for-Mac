# Battery Guardian

**A macOS battery forensics tool that detects counterfeit, reprogrammed, and spoofed MacBook batteries.**

Battery Guardian reads battery-gauge telemetry exposed by macOS and evaluates it with a versioned, model-aware forensic policy. It records nine possible signals, but only supported signals for the detected gauge profile can affect a verdict.

Battery Guardian detects contradictions and known reset signatures. It does not cryptographically prove that a battery is Apple-original.

---

## Why This Exists

The MacBook battery replacement market is flooded with counterfeit and reprogrammed chips. These batteries:
- Report 100% health regardless of actual cell condition
- Show falsified cycle counts
- Clone another battery's serial number
- Silently degrade without warning

Existing tools (CoconutBattery, iStatMenus, system profiler) only read and display the data the chip reports. They have no way to tell you if that data is real.

Battery Guardian doesn't just display the data — it **audits it** against documented register relationships and labelled empirical signatures, while reporting when the available evidence is insufficient.

---

## Features

- **9 documented forensic signals** — activated only where the gauge profile and evidence support them
- **Instant results** — single `ioreg` snapshot, no waiting
- **Physics-based scoring** — weighted penalty system with documented thresholds
- **Monthly history trends** — track health and cycles over time automatically
- **Operating-time history** — shown as powered-on time, not mislabelled as a manufacture date
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

TI gauge families share concepts, but register meanings, defaults, units, and availability vary by model. Battery Guardian therefore selects an explicit profile and refuses to make an authenticity conclusion when required evidence is unavailable.

Data is read using:
```bash
ioreg -l -w0 -r -c AppleSmartBattery
```

### The 9 Forensic Signals

The policy currently models reset signatures, Qmax consistency, capacity relationships, DOD0 records, clock integrity, calibration timeline, pack voltage, historical continuity, and DataFlash writes. Some remain observation-only until their model mapping and classification threshold have enough primary documentation and labelled validation.

---

| Signal | Current policy |
|---|---|
| Model-specific reset signature | Active for `bq20z451`; requires the combined cycle, DOD0-sentinel, and zero-write pattern |
| Calibration timeline | Active when the mapped lifetime fields are present |
| Clock integrity | Active when the profile exposes both counters and enough samples exist |
| Qmax consistency | Observation-only pending labelled validation |
| Capacity relationship | Observation-only pending labelled validation |
| DOD0 records | Profile evidence; identical non-sentinel values are not a universal failure |
| Pack voltage | Disabled pending hardware/topology profiles |
| Historical continuity | Observation-only; elapsed wall time alone is not enough |
| DataFlash writes | Used only as part of a validated profile-specific pattern |

The authoritative modes, thresholds, evidence levels, and minimum fields live in [`forensics/contract.json`](forensics/contract.json). Python and Swift tests run the same archived fixtures against this contract.

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

**Current verdicts:**
- `score ≥ 40` → **SPOOFED**
- `score > 0` → **SUSPICIOUS**
- supported evidence complete, `score = 0` → **NO_ANOMALIES**
- required evidence missing or gauge unsupported → **INSUFFICIENT_EVIDENCE**
- scan failure → **ERROR**

`NO_ANOMALIES` means the active supported checks found no contradiction. It is not proof of manufacturer provenance.

---

## Requirements

**Native v2:**
- macOS 14 Sonoma or later
- MacBook with a built-in battery (not compatible with Mac Mini, iMac, Mac Pro, Mac Studio)
- Python 3.9+ (for running from source only)

**Planned platform support:**
- 📱 iPhone / iPad battery forensics
- 💻 Windows laptop battery support

---

## Install (Pre-built)

1. Download the current notarized archive from [Releases](https://github.com/Dannyjay-hub/Battery-Guardian-for-Mac/releases)
2. Unzip it and drag **Battery Guardian** to Applications
3. Open it normally. A release is not published until strict signature, notarization-ticket, and extracted-archive verification pass.

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

Native releases are built from the Xcode project:

```bash
TEAM_ID=YOUR_TEAM_ID ./native/build_release.sh
```

The script signs, notarizes, staples, packages, extracts, and re-verifies the exact ZIP users receive. `build_release.sh` remains only for reproducible legacy Python v1.x builds.

---

## Project Structure

```
Battery Guardian/
├── battery_guardian_web.py   # Entry point — server, CLI, window management
├── bg_forensics.py           # Shared Python implementation of the forensic contract
├── forensics/                # Versioned policy and cross-language evidence fixtures
├── native/                   # SwiftUI v2 app, tests, and release pipeline
├── bg_scanner.py             # Legacy Python scan orchestration
├── bg_analysis.py            # Pure analysis functions (parsing, scoring, trends)
├── bg_automation.py          # LaunchAgent installer and share report generator
├── bg_config.py              # Scoring constants and configuration
├── bg_state.py               # Shared mutable scan state (thread-safe)
├── bg_history.py             # Per-scan history persistence (JSON)
├── bg_platform.py            # Platform detection and Mac model identification
├── bg_server.py              # HTTP request handler for the web UI
├── bg_template.html          # Frontend UI (HTML/CSS/JS)
├── bg_guide.html             # Forensic methodology guide page
├── dmg_background.png        # DMG window background
└── build_release.sh          # Legacy PyInstaller + DMG build script
```

---

## How to Contribute

Battery Guardian is open source and contributions are welcome. Areas where help would be great:

- **Expanding the forensic engine** — additional DataFlash register checks
- **iPhone/iPad support** — extending forensics to Apple mobile batteries
- **Native engine validation** — expand model profiles and cross-language evidence fixtures
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
