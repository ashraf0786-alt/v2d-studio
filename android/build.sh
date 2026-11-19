#!/usr/bin/env bash
# Build a signed WebView APK using native aapt for a valid AndroidManifest.xml.
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
BT="/opt/android-sdk/android-14"          # d8 / apksigner (Java tools)
JAR="${ANDROID_JAR:-/tmp/opencode/api29/android-10/android.jar}"
AAPT="$(command -v aapt || echo aapt)"
LABEL="${APP_LABEL:-V2D Studio}"

[ -f "$JAR" ] || { echo "Missing android.jar at $JAR"; exit 1; }
command -v "$AAPT" >/dev/null || { echo "Missing aapt"; exit 1; }

rm -rf "$DIR/build"
mkdir -p "$DIR/build/classes" "$DIR/build/gen"

echo "==> generating binary AndroidManifest.xml with aapt"
"$AAPT" package -f -m -J "$DIR/build/gen" -M "$DIR/AndroidManifest.xml" \
  -S "$DIR/res" -I "$JAR" -F "$DIR/build/base.apk"

echo "==> compiling Java"
javac -source 8 -target 8 -nowarn -bootclasspath "$JAR" \
  -d "$DIR/build/classes" -cp "$JAR" \
  "$DIR/src/com/v2dstudio/app/MainActivity.java" 2>&1 | grep -v "bootstrap class path" || true

echo "==> dexing"
"$BT/d8" --lib "$JAR" --min-api 21 --output "$DIR/build" \
  "$DIR/build/classes/com/v2dstudio/app/MainActivity.class"

echo "==> packaging (aligned)"
python3 - "$DIR" <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from repack import repack
d = Path(sys.argv[1])
repack(d / "build" / "base.apk", d / "build" / "unsigned.apk",
       {"classes.dex": d / "build" / "classes.dex"})
PY

echo "==> signing (v1 + v2 + v3)"
if [ ! -f "$DIR/debug.jks" ]; then
  keytool -genkeypair -keystore "$DIR/debug.jks" -storepass android -keypass android \
    -alias v2d -keyalg RSA -keysize 2048 -validity 10000 \
    -dname "CN=V2D Studio, OU=Mobile, O=V2D Studio, L=NA, ST=NA, C=US" >/dev/null 2>&1
fi
"$BT/apksigner" sign --v1-signing-enabled true --v2-signing-enabled true --v3-signing-enabled true \
  --ks "$DIR/debug.jks" --ks-pass pass:android --key-pass pass:android \
  --out "$DIR/V2DStudio.apk" "$DIR/build/unsigned.apk"
"$BT/apksigner" verify --verbose --print-certs "$DIR/V2DStudio.apk" | head -14

echo "APK: $DIR/V2DStudio.apk"
ls -lh "$DIR/V2DStudio.apk"
