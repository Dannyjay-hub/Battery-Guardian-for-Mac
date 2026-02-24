#!/bin/bash
cd "$(dirname "$0")"

echo "Launching Mac Battery Guardian (Web Edition)..."
echo "This will open in your browser."

# We prefer python3. 
# Since we removed the specific GUI library dependency, ANY python3 will work now.
PYTHON_CMD="python3"
if [ -f "/usr/bin/python3" ]; then
    PYTHON_CMD="/usr/bin/python3"
fi

"$PYTHON_CMD" battery_guardian_web.py

# Keep window open if it crashes
EXIT_CODE=$?
if [ $EXIT_CODE -ne 0 ]; then
    echo "Error detected. Press Enter to close."
    read -p ""
fi
exit
