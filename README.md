# 🔋 Battery Guardian v1.1

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Platform: macOS](https://img.shields.io/badge/Platform-macOS-black.svg)](https://www.apple.com/macos/)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-yellow.svg)](https://www.python.org/)

A native macOS app that detects counterfeit, reprogrammed, or spoofed MacBook batteries by analyzing the Texas Instruments gas gauge chip data.

## Features
- **Battery Health Score (0-100)** — Composite forensic rating
- **Quick Scan (10s) & Full Scan (60s)** — Two scan modes with live countdown
- **Spoof Detection** — Zero Entropy, Voltage Flatline, Odometer Rollback, Time Paradox
- **Real-Time Metrics** — Cycles, health %, entropy, operating time, temperature
- **Trend Tracking** — Compare scans over time with ↑↓→ arrows
- **Automation** — Schedule silent daily scans via launchd
- **Share Report** — Copy results to clipboard
- **Native Window** — Runs as a real macOS app (no browser needed)

## Installation

### Option A: DMG (Recommended)
1. Download the latest DMG from [Releases](https://github.com/Dannyjay-hub/Battery-Guardian-for-Mac/releases)
2. Open the DMG
3. Drag **Battery Guardian** to **Applications**
4. Double-click to launch

### Option B: Run from Source
```bash
git clone https://github.com/Dannyjay-hub/Battery-Guardian-for-Mac.git
cd Battery-Guardian-for-Mac
pip3 install -r requirements.txt
python3 battery_guardian_web.py
```

## CLI Options
```bash
python3 battery_guardian_web.py              # Launch GUI
python3 battery_guardian_web.py --auto       # Headless scan (log only)
python3 battery_guardian_web.py --no-window  # Use browser instead of native window
python3 battery_guardian_web.py --enable-automation 30  # Schedule daily scans
```

## Requirements
- macOS 11+ (Big Sur or later)
- MacBook with built-in battery
- Python 3.9+
- Dependencies: `pip3 install -r requirements.txt`

## Troubleshooting
- **"Permission Denied"**: Run `chmod +x "Double Click To Run.command"`
- **"File is damaged"**: Run `xattr -cr "Double Click To Run.command"`
- **No window appears**: Try `--no-window` flag for browser fallback

## Build from Source
```bash
chmod +x build_dmg.sh
./build_dmg.sh
```

## License
[MIT](LICENSE) — Daniel Jesusegun ([@Dannyjay-hub](https://github.com/Dannyjay-hub))
