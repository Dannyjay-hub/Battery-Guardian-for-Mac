Mac Battery Guardian v5.8 (Custom Auto + UI)
==============================================

USAGE:
1. Double-click "Double Click To Run.command".
2. It will open in your browser automatically.


TROUBLESHOOTING:
- ERROR 1: "Permission Denied" or "You do not have appropriate access privileges":
    1. Open Terminal.
    2. Paste this command and hit Enter:
       chmod +x "Double Click To Run.command"
    3. Try opening it again.

- ERROR 2: "File is damaged" or "Unidentified Developer":
    1. Open Terminal.
    2. Paste this command and hit Enter:
       xattr -cr "Double Click To Run.command"
    3. Try opening it again.
- Logs are saved to: ~/.battery_guardian_log.json

AUTOMATION (CUSTOMIZABLE):
You can now schedule silent background scans tailored to your needs.
1. Look for the "Automate Daily Scans" section (Green Box) in the browser.
2. Enter the **Custom Days** (e.g., 7).
3. Enter the **Start Time** (e.g., 20:00 for 8 PM).
4. Click "Enable".
5. Enter your password if prompted (to allow the launchd agent).

ADVANCED / HEADLESS:
- Run silent scan: python3 battery_guardian_web.py --auto
- Enable automation via CLI: python3 battery_guardian_web.py --enable-automation 5

GITHUB UPDATES:
This tool is connected to Git. When a new version is released, you don't need to download a zip.
To get the latest updates:
1. Open Terminal.
2. Type `cd ` (with a space) and drag the "Battery Guardian" folder into the terminal window.
3. Hit Enter.
4. Type `git pull` and hit Enter.
5. It will download the changes and update your files automatically.
