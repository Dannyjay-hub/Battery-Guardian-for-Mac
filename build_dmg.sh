#!/bin/bash
# build_dmg.sh — Builds Battery Guardian.app and Battery Guardian.dmg
# Usage: ./build_dmg.sh

set -e

APP_NAME="Battery Guardian"
VERSION="1.0"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_DIR="$SCRIPT_DIR/build"
APP_BUNDLE="$BUILD_DIR/$APP_NAME.app"
DMG_NAME="BatteryGuardian_v${VERSION}.dmg"
DMG_PATH="$SCRIPT_DIR/$DMG_NAME"

echo "=== Building $APP_NAME v$VERSION ==="

# Clean previous build
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

# --- 1. Create .app bundle ---
echo "[1/5] Creating .app bundle..."
mkdir -p "$APP_BUNDLE/Contents/MacOS"
mkdir -p "$APP_BUNDLE/Contents/Resources"

# Info.plist
cat > "$APP_BUNDLE/Contents/Info.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>Battery Guardian</string>
    <key>CFBundleDisplayName</key>
    <string>Battery Guardian</string>
    <key>CFBundleIdentifier</key>
    <string>com.dannyjay.batteryguardian</string>
    <key>CFBundleVersion</key>
    <string>${VERSION}</string>
    <key>CFBundleShortVersionString</key>
    <string>${VERSION}</string>
    <key>CFBundleExecutable</key>
    <string>launcher</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>LSMinimumSystemVersion</key>
    <string>11.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>LSUIElement</key>
    <false/>
</dict>
</plist>
PLIST

# PkgInfo
echo "APPL????" > "$APP_BUNDLE/Contents/PkgInfo"

# Copy icon
if [ -f "$SCRIPT_DIR/AppIcon.icns" ]; then
    cp "$SCRIPT_DIR/AppIcon.icns" "$APP_BUNDLE/Contents/Resources/AppIcon.icns"
    echo "    Icon: copied"
else
    echo "    Warning: AppIcon.icns not found, skipping"
fi

# Copy Python script
cp "$SCRIPT_DIR/battery_guardian_web.py" "$APP_BUNDLE/Contents/Resources/battery_guardian_web.py"
echo "    Script: copied"

# --- 2. Create launcher shell script ---
echo "[2/5] Creating launcher..."
cat > "$APP_BUNDLE/Contents/MacOS/launcher" << 'LAUNCHER'
#!/bin/bash
# Battery Guardian Launcher
DIR="$(cd "$(dirname "$0")/../Resources" && pwd)"
PYTHON=""

# Find Python 3
for p in /usr/bin/python3 /usr/local/bin/python3 /opt/homebrew/bin/python3; do
    if [ -x "$p" ]; then
        PYTHON="$p"
        break
    fi
done

# Fallback
if [ -z "$PYTHON" ]; then
    PYTHON=$(which python3 2>/dev/null)
fi

if [ -z "$PYTHON" ]; then
    osascript -e 'display alert "Python 3 Required" message "Battery Guardian requires Python 3. Please install it from python.org or via Homebrew." as critical'
    exit 1
fi

# Check pywebview
$PYTHON -c "import webview" 2>/dev/null
if [ $? -ne 0 ]; then
    osascript -e 'display alert "Installing Dependencies" message "First launch: installing pywebview..." as informational giving up after 3'
    $PYTHON -m pip install pywebview 2>/dev/null || $PYTHON -m pip install --user pywebview 2>/dev/null
fi

# Launch
exec "$PYTHON" "$DIR/battery_guardian_web.py"
LAUNCHER

chmod +x "$APP_BUNDLE/Contents/MacOS/launcher"
echo "    Launcher: created"

# --- 3. Ad-hoc sign ---
echo "[3/5] Signing..."
codesign --force --deep --sign - "$APP_BUNDLE" 2>/dev/null && echo "    Signed: ad-hoc" || echo "    Signing skipped (non-critical)"

# --- 4. Create DMG ---
echo "[4/5] Creating DMG..."
rm -f "$DMG_PATH"

# Create temp DMG folder
DMG_TEMP="/tmp/bg_dmg_$$"
rm -rf "$DMG_TEMP"
mkdir -p "$DMG_TEMP"
cp -R "$APP_BUNDLE" "$DMG_TEMP/"
ln -s /Applications "$DMG_TEMP/Applications"

hdiutil create -volname "$APP_NAME" \
    -srcfolder "$DMG_TEMP" \
    -ov -format UDZO \
    "$DMG_PATH" >/dev/null 2>&1

rm -rf "$DMG_TEMP"
echo "    DMG: created"

# --- 5. Done ---
echo "[5/5] Complete!"
echo ""
echo "  App:  $APP_BUNDLE"
echo "  DMG:  $DMG_PATH"
echo "  Size: $(du -sh "$DMG_PATH" | awk '{print $1}')"
echo ""
echo "To install: Open the DMG and drag Battery Guardian to Applications."
