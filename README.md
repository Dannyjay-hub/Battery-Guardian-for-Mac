# Battery Guardian v1.0

A native macOS app that detects counterfeit, reprogrammed, or spoofed MacBook batteries.

## Features
- **Battery Health Score (0-100)** — Composite forensic score
- **Quick Scan (10s) & Full Scan (60s)** — Two scan modes
- **Spoof Detection** — Zero Entropy, Voltage Flatline, Odometer Rollback, Time Paradox checks
- **Trend Tracking** — Compare scans over time with ↑↓→ arrows
- **Automation** — Schedule silent daily scans via launchd
- **Share Report** — Copy results to clipboard
- **Native Window** — Runs as a real macOS app (no browser)

## Installation

### Option A: DMG (Recommended)
1. Download `BatteryGuardian_v1.0.dmg`
2. Open the DMG
3. Drag **Battery Guardian** to **Applications**
4. Double-click to launch

### Option B: Run from Source
1. Install Python 3 (if not already installed)
2. Install pywebview: `pip3 install pywebview`
3. Run: `python3 battery_guardian_web.py`

## CLI Options
- `python3 battery_guardian_web.py` — Launch GUI
- `python3 battery_guardian_web.py --auto` — Headless scan (log only)
- `python3 battery_guardian_web.py --no-window` — Use browser instead of native window
- `python3 battery_guardian_web.py --enable-automation 30` — Schedule daily scans for 30 days

## Requirements
- macOS 11+ (Big Sur or later)
- MacBook with built-in battery (Mac Mini/iMac/Mac Pro not supported)
- Python 3.9+
- pywebview (`pip3 install pywebview`)

## Troubleshooting
- **"Permission Denied"**: Run `chmod +x "Double Click To Run.command"`
- **"File is damaged"**: Run `xattr -cr "Double Click To Run.command"`
- **No window appears**: Try `python3 battery_guardian_web.py --no-window` to use browser fallback

## Build from Source
```bash
chmod +x build_dmg.sh
./build_dmg.sh
```
This creates `Battery Guardian.app` and `BatteryGuardian_v1.0.dmg`.

## License
MIT

## Author
[@Dannyjay-hub](https://github.com/Dannyjay-hub)
