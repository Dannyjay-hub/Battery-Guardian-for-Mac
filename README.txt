Mac Battery Guardian v5.6 (Fix)
================================

USAGE:
1. Double-click "Double Click To Run.command".
2. It will open in your browser automatically.
3. If it asks for permission to access "System Events" or "Terminal", click Allow.

CHANGELOG (v5.6):
- Fixed "Error detected" crash on launch.
- Added auto-port detection (will try 8080, 8081, 8082... if port is busy).
- Enabled error logging for easier debugging.

TROUBLESHOOTING:
- If it says "File is damaged", open Terminal and run:
  xattr -cr "Double Click To Run.command"
- If it still crashes, take a screenshot of the window; it now shows the real error.
