#!/bin/bash
# build_release.sh — Builds Battery Guardian standalone App using PyInstaller
# Produces both a ZIP (fallback) and a styled DMG installer.
# Usage: ./build_release.sh

set -e

APP_NAME="Battery Guardian"
VERSION="1.3.2"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_DIR="$SCRIPT_DIR/build"
DIST_DIR="$SCRIPT_DIR/dist"
ZIP_NAME="BatteryGuardian_v${VERSION}.zip"
ZIP_PATH="$SCRIPT_DIR/$ZIP_NAME"
DMG_NAME="BatteryGuardian_v${VERSION}.dmg"
DMG_PATH="$SCRIPT_DIR/$DMG_NAME"

echo "=== Building $APP_NAME v$VERSION with PyInstaller ==="

# Clean previous builds
rm -rf "$BUILD_DIR"
rm -rf "$DIST_DIR"
rm -f "$ZIP_PATH" "$DMG_PATH" "$SCRIPT_DIR/tmp_rw.dmg"

# --- 1. Compile to standalone .app using PyInstaller ---
echo "[1/5] Compiling macOS standalone binary..."
python3 -m PyInstaller --name "$APP_NAME" \
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


# --- 2. Refine Info.plist ---
echo "[2/5] Refining Info.plist..."
PLIST_PATH="$APP_BUNDLE/Contents/Info.plist"
if [ -f "$PLIST_PATH" ]; then
    defaults write "$PLIST_PATH" NSHighResolutionCapable -bool YES
    defaults write "$PLIST_PATH" CFBundleShortVersionString "$VERSION"
    defaults write "$PLIST_PATH" CFBundleIdentifier "com.dannyjay.batteryguardian"
    plutil -convert xml1 "$PLIST_PATH"
fi


# --- 3. Ad-hoc sign ---
echo "[3/5] Signing payload..."
codesign --force --deep --sign - "$APP_BUNDLE" 2>/dev/null && echo "    Signed: ad-hoc" || echo "    Signing skipped (non-critical)"


# --- 4. Create ZIP Archive (fallback) ---
echo "[4/5] Creating ZIP deployment package..."
cd "$DIST_DIR"
zip -r -9 -y "$ZIP_PATH" "$APP_NAME.app" > /dev/null 2>&1
cd "$SCRIPT_DIR"
echo "    ZIP: $ZIP_PATH ($(du -sh "$ZIP_PATH" | awk '{print $1}'))"


# --- 5. Create styled DMG installer ---
echo "[5/5] Creating styled DMG installer..."

TMP_DMG="$SCRIPT_DIR/tmp_rw.dmg"
VOLUME_NAME="$APP_NAME"
STAGING_DIR="$(mktemp -d)"

# Stage ALL DMG contents (including symlink and background)
cp -r "$APP_BUNDLE" "$STAGING_DIR/$APP_NAME.app"
cp "$SCRIPT_DIR/ReadMeFirst.html" "$STAGING_DIR/ReadMeFirst.html"
ln -sf /Applications "$STAGING_DIR/Applications"
mkdir -p "$STAGING_DIR/.background"
cp "$SCRIPT_DIR/dmg_background.png" "$STAGING_DIR/.background/background.png"

# Create a writable DMG from the fully-staged directory
hdiutil create -srcfolder "$STAGING_DIR" \
               -volname "$VOLUME_NAME" \
               -fs HFS+ \
               -format UDRW \
               -size 120m \
               "$TMP_DMG" > /dev/null 2>&1

rm -rf "$STAGING_DIR"

# Mount for AppleScript styling only (no file writes needed)
DEVICE=$(hdiutil attach -readwrite -noverify -noautoopen "$TMP_DMG" | awk 'END{print $1}')
MOUNT_POINT="/Volumes/$VOLUME_NAME"

# Style the Finder window
osascript <<APPLESCRIPT
tell application "Finder"
    tell disk "$VOLUME_NAME"
        open
        set current view of container window to icon view
        set toolbar visible of container window to false
        set statusbar visible of container window to false
        set the bounds of container window to {100, 100, 760, 500}
        set viewOptions to the icon view options of container window
        set arrangement of viewOptions to not arranged
        set icon size of viewOptions to 120
        set background picture of viewOptions to file ".background:background.png"
        set position of item "$APP_NAME.app" of container window to {180, 240}
        set position of item "Applications" of container window to {480, 240}
        set position of item "ReadMeFirst.html" of container window to {330, 65}
        close
        open
        update without registering applications
        delay 2
    end tell
end tell
APPLESCRIPT

# Sync, unmount, convert to read-only compressed DMG
sync
hdiutil detach "$DEVICE" > /dev/null 2>&1
hdiutil convert "$TMP_DMG" -format UDZO -imagekey zlib-level=9 -o "$DMG_PATH" > /dev/null 2>&1
rm -f "$TMP_DMG"

echo "    DMG: $DMG_PATH ($(du -sh "$DMG_PATH" | awk '{print $1}'))"

echo ""
echo "Build complete!"
echo "  ZIP ($(du -sh "$ZIP_PATH" | awk '{print $1}')): $ZIP_NAME"
echo "  DMG ($(du -sh "$DMG_PATH" | awk '{print $1}')): $DMG_NAME"
echo "  Ready to deploy."
