#!/usr/bin/env bash
# Build a signed WebView APK for the V2D Studio web app.
# Usage: APP_URL=https://your-public-host ./android/build.sh
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
SDK="${ANDROID_SDK:-/opt/android-sdk}"
BT="$SDK/android-14"          # d8 / apksigner / zipalign (Java tools)
JAR="$SDK/android-35/android.jar"
APP_URL="${APP_URL:-https://example.com}"
APP_LABEL="${APP_LABEL:-V2D Studio}"
PACKAGE="com.v2dstudio.app"

[ -f "$JAR" ] || { echo "Missing android.jar at $JAR"; exit 1; }
[ -f "$BT/d8" ] || { echo "Missing d8 at $BT"; exit 1; }

rm -rf "$DIR/build"
mkdir -p "$DIR/build/classes"

echo "==> generating binary AndroidManifest.xml"
python3 "$DIR/build_axml.py" "$DIR/build/AndroidManifest.xml" "$PACKAGE" "$APP_LABEL"

echo "==> compiling Java"
javac -source 8 -target 8 -nowarn -bootclasspath "$JAR" \
  -d "$DIR/build/classes" -cp "$JAR" \
  "$DIR/src/com/v2dstudio/app/MainActivity.java" 2>&1 | grep -v "bootstrap class path" || true

echo "==> dexing"
"$BT/d8" --lib "$JAR" --min-api 21 --output "$DIR/build" \
  "$DIR/build/classes/com/v2dstudio/app/MainActivity.class"

echo "==> packaging unsigned APK"
python3 - "$DIR" <<'PY'
import sys, zipfile, pathlib
d = pathlib.Path(sys.argv[1])
unsigned = d / "build" / "unsigned.apk"
with zipfile.ZipFile(unsigned, "w", zipfile.ZIP_DEFLATED) as z:
    z.write(d / "build" / "AndroidManifest.xml", "AndroidManifest.xml")
    z.write(d / "build" / "classes.dex", "classes.dex")
PY

echo "==> signing"
# zipalign in the local SDK is x86-only; all entries here are deflated, so
# alignment is not required for installability.
if [ ! -f "$DIR/debug.jks" ]; then
  keytool -genkeypair -keystore "$DIR/debug.jks" -storepass android -keypass android \
    -alias v2d -keyalg RSA -keysize 2048 -validity 10000 \
    -dname "CN=V2D Studio, OU=Mobile, O=V2D Studio, L=NA, S=NA, C=US" >/dev/null 2>&1
fi
"$BT/apksigner" sign --ks "$DIR/debug.jks" --ks-pass pass:android --key-pass pass:android \
  --out "$DIR/V2DStudio.apk" "$DIR/build/unsigned.apk"
"$BT/apksigner" verify --print-certs "$DIR/V2DStudio.apk" | head -6

echo "APK: $DIR/V2DStudio.apk"
ls -lh "$DIR/V2DStudio.apk"
