#!/bin/bash
# Build, sign, notarize, staple, package, and verify the native release.
# Required once per Mac:
#   xcrun notarytool store-credentials BatteryGuardianNotary ...
# Required for each run:
#   TEAM_ID=XXXXXXXXXX ./native/build_release.sh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PROJECT="$ROOT_DIR/native/BatteryGuardian.xcodeproj"
SCHEME="BatteryGuardian"
ARCHIVE_PATH="$ROOT_DIR/build/native/BatteryGuardian.xcarchive"
RELEASE_ROOT="$ROOT_DIR/dist/native"
SIGNING_IDENTITY="${SIGNING_IDENTITY:-Developer ID Application}"
NOTARY_PROFILE="${NOTARY_PROFILE:-BatteryGuardianNotary}"

if [[ -z "${TEAM_ID:-}" ]]; then
    echo "TEAM_ID is required (the 10-character Apple Developer Team ID)."
    exit 1
fi

VERSION="$(xcodebuild -project "$PROJECT" -scheme "$SCHEME" -showBuildSettings 2>/dev/null | awk '/MARKETING_VERSION/ {print $3; exit}')"
if [[ -z "$VERSION" ]]; then
    echo "Could not read MARKETING_VERSION from the Xcode project."
    exit 1
fi

RELEASE_DIR="$RELEASE_ROOT/v$VERSION"
UPLOAD_ZIP="$RELEASE_DIR/BatteryGuardian_v${VERSION}_notarization.zip"
FINAL_ZIP="$RELEASE_DIR/BatteryGuardian_v${VERSION}.zip"

rm -rf "$ARCHIVE_PATH" "$RELEASE_DIR"
mkdir -p "$RELEASE_DIR"

echo "Building and signing Battery Guardian v$VERSION..."
xcodebuild archive \
    -project "$PROJECT" \
    -scheme "$SCHEME" \
    -configuration Release \
    -destination "generic/platform=macOS" \
    -archivePath "$ARCHIVE_PATH" \
    DEVELOPMENT_TEAM="$TEAM_ID" \
    CODE_SIGN_STYLE=Manual \
    CODE_SIGN_IDENTITY="$SIGNING_IDENTITY"

APP_PATH="$ARCHIVE_PATH/Products/Applications/BatteryGuardian.app"
if [[ ! -d "$APP_PATH" ]]; then
    echo "Archive completed without the expected app: $APP_PATH"
    exit 1
fi

codesign --verify --deep --strict --verbose=2 "$APP_PATH"

# Apple's ZIP transport preserves the signed bundle without recursively writing
# AppleDouble files into it. The upload archive is temporary.
ditto -c -k --keepParent "$APP_PATH" "$UPLOAD_ZIP"
xcrun notarytool submit "$UPLOAD_ZIP" --keychain-profile "$NOTARY_PROFILE" --wait
rm -f "$UPLOAD_ZIP"

xcrun stapler staple "$APP_PATH"
xcrun stapler validate "$APP_PATH"

# Xcode can attach local provenance metadata to every file in the bundle.
# That metadata is not part of the signature or notarization ticket, but ditto
# serializes it as AppleDouble `._` entries. Strip it before distribution so
# non-Finder ZIP extractors cannot materialize extra files inside the app.
xattr -cr "$APP_PATH"
codesign --verify --deep --strict --verbose=2 "$APP_PATH"
spctl --assess --type execute --verbose=2 "$APP_PATH"
xcrun stapler validate "$APP_PATH"

COPYFILE_DISABLE=1 ditto -c -k --norsrc --noextattr --keepParent "$APP_PATH" "$FINAL_ZIP"

# Inspect the raw archive too. A normal unzip utility would otherwise restore
# AppleDouble entries as real files and invalidate the signed bundle.
if unzip -Z1 "$FINAL_ZIP" | grep -Eq '(^|/)\._|(^|/)__MACOSX(/|$)'; then
    echo "Packaging error: AppleDouble metadata was found in the release ZIP."
    exit 1
fi

# Verify exactly what users receive after extraction with a standard ZIP tool.
VERIFY_DIR="$(mktemp -d)"
unzip -q "$FINAL_ZIP" -d "$VERIFY_DIR"
codesign --verify --deep --strict --verbose=2 "$VERIFY_DIR/BatteryGuardian.app"
xcrun stapler validate "$VERIFY_DIR/BatteryGuardian.app"
if find "$VERIFY_DIR/BatteryGuardian.app" -name '._*' -print -quit | grep -q .; then
    echo "Packaging error: AppleDouble files were found inside the extracted app."
    exit 1
fi
rm -rf "$VERIFY_DIR"

shasum -a 256 "$FINAL_ZIP" > "$FINAL_ZIP.sha256"
echo "Release ready: $FINAL_ZIP"
echo "SHA-256: $(awk '{print $1}' "$FINAL_ZIP.sha256")"
