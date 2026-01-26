Mac Battery Guardian v5.8 (Custom Auto + UI)
==============================================

USAGE:
1. Double-click "Double Click To Run.command".
2. It will open in your browser automatically.
3. You will see your Mac's Model and Serial in the header.

AUTOMATION (CUSTOMIZABLE):
You can now schedule silent background scans tailored to your needs.
1. Look for the "Automate Daily Scans" section (Green Box).
2. Enter the **Number of Days** (e.g., 7).
3. Enter the **Start Time** (e.g., 20:00 for 8 PM).
4. Click "Enable".
5. Enter your password if prompted (to allow the launchd agent).

ADVANCED / HEADLESS:
- Run silent scan: python3 battery_guardian_web.py --auto
- Enable automation via CLI: python3 battery_guardian_web.py --enable-automation 5

GITHUB UPDATES:
This tool is Git-enabled. To update:
  git pull

TROUBLESHOOTING:
- If "File is damaged", run: xattr -cr "Double Click To Run.command"
- Logs are saved to: ~/.battery_guardian_history.json
