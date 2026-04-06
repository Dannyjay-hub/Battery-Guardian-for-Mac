#!/bin/bash
# build_dmg.sh — Builds Battery Guardian standalone App using PyInstaller
# Usage: ./build_dmg.sh

set -e

APP_NAME="Battery Guardian"
VERSION="1.3"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_DIR="$SCRIPT_DIR/build"
DIST_DIR="$SCRIPT_DIR/dist"
ZIP_NAME="BatteryGuardian_v${VERSION}.zip"
ZIP_PATH="$SCRIPT_DIR/$ZIP_NAME"

echo "=== Building $APP_NAME v$VERSION with PyInstaller ==="

# Clean previous builds
rm -rf "$BUILD_DIR" 
rm -rf "$DIST_DIR"
rm -f "$ZIP_PATH"

# --- 1. Compile to standalone .app using PyInstaller ---
echo "[1/4] Compiling macOS standalone binary..."
# Note: pywebview and other modules are automatically detected and bundled.
pyinstaller --name "$APP_NAME" \
            --windowed \
            --noconfirm \
            --clean \
            --icon "$SCRIPT_DIR/AppIcon.icns" \
            --add-data "$SCRIPT_DIR/bg_template.html:." \
            --add-data "$SCRIPT_DIR/bg_guide.html:." \
            "$SCRIPT_DIR/battery_guardian_web.py" > /dev/null 2>&1

APP_BUNDLE="$DIST_DIR/$APP_NAME.app"

if [ ! -d "$APP_BUNDLE" ]; then
    echo "Error: PyInstaller failed to build the .app bundle."
    exit 1
fi

echo "    Compilation complete: $APP_BUNDLE"


# --- 2. Minimal tuning & Plist override (Optional but good) ---
echo "[2/4] Refining Info.plist..."
PLIST_PATH="$APP_BUNDLE/Contents/Info.plist"
if [ -f "$PLIST_PATH" ]; then
    # Modify the default PyInstaller plist minimally if needed
    # Usually PyInstaller plist is fine, but we can ensure high-res capable
    defaults write "$PLIST_PATH" NSHighResolutionCapable -bool YES
    defaults write "$PLIST_PATH" CFBundleShortVersionString "$VERSION"
    defaults write "$PLIST_PATH" CFBundleIdentifier "com.dannyjay.batteryguardian"
    # Convert binary plist back to xml for readability
    plutil -convert xml1 "$PLIST_PATH"
fi


# --- 3. Ad-hoc sign ---
echo "[3/4] Signing payload..."
codesign --force --deep --sign - "$APP_BUNDLE" 2>/dev/null && echo "    Signed: ad-hoc" || echo "    Signing skipped (non-critical)"


# --- 4. Create ZIP Archive ---
echo "[4/4] Creating ZIP deployment package..."
rm -f "$ZIP_PATH"

cd "$DIST_DIR"
# Archive the App bundle recursively, preserving symlinks
zip -r -9 -y "$ZIP_PATH" "$APP_NAME.app" >/dev/null 2>&1
cd "$SCRIPT_DIR"

echo "    ZIP archive properly compressed: $ZIP_PATH"

echo ""
echo "[5/5] Complete!"
echo "  Archive Size: $(du -sh "$ZIP_PATH" | awk '{print $1}')"
echo "  Ready to deploy."
