Mac Battery Guardian v5.7 (Auto + UI)
=======================================

USAGE:
1. Double-click "Double Click To Run.command".
2. It will open in your browser automatically.
3. You will see your Mac's Model and Serial in the header.

AUTOMATION (NEW):
You can now enable daily scans directly from the App Interface.
1. Look for the green "Automate Daily Scans" box.
2. Click "Enable".
3. Enter your password if prompted (to allow the background agent).
4. The tool will wake up at 8:00 PM silently for the next 7 days.

ADVANCED / HEADLESS:
- Run silent scan: python3 battery_guardian_web.py --auto
- Enable automation via CLI: python3 battery_guardian_web.py --enable-automation 5

GITHUB UPDATES:
This tool is Git-enabled. To update:
  git pull

TROUBLESHOOTING:
- If "File is damaged", run: xattr -cr "Double Click To Run.command"
- Logs are saved to: ~/.battery_guardian_history.json
