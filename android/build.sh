#!/usr/bin/env bash
# Build the collector without Android Studio.
#
# The toolchain is a plain unzipped JDK and Android SDK under
# ~/android-toolchain — nothing is installed system-wide and nothing needs
# admin rights. See TOOLCHAIN.md to recreate it on another machine.
#
#   ./build.sh test            run the unit tests (no device needed)
#   ./build.sh assembleDebug   build the installable debug APK
#   ./build.sh                 both
set -euo pipefail

TOOLCHAIN="${TOOLCHAIN:-$HOME/android-toolchain}"
JDK="$(find "$TOOLCHAIN" -maxdepth 1 -type d -name 'jdk-*' | head -1)"

if [ -z "$JDK" ]; then
    echo "No JDK under $TOOLCHAIN — see TOOLCHAIN.md" >&2
    exit 1
fi

export JAVA_HOME="$JDK"
export ANDROID_HOME="$TOOLCHAIN/sdk"

# Gradle's daemon opens an AF_UNIX socket in the temp directory, and that
# connect() fails on Windows when the path contains a space — which
# "C:\Users\Acer Nitro 5\AppData\Local\Temp" does. Gradle reports only
# "Unable to establish loopback connection", naming nothing useful.
#
# JAVA_TOOL_OPTIONS reaches every JVM Gradle forks, which org.gradle.jvmargs
# alone does not: the launcher JVM needs it too.
mkdir -p /c/Temp 2>/dev/null || true
export JAVA_TOOL_OPTIONS="-Djdk.net.unixdomain.tmpdir=C:\\Temp"

cd "$(dirname "$0")"

# Written here rather than committed: it holds a machine-local SDK path.
# Forward slashes on purpose — a backslash is an escape character in a
# .properties file, and the resulting path fails with a syntax error that
# names neither the file nor the reason.
if [ ! -f local.properties ]; then
    printf 'sdk.dir=%s\n' "$(cygpath -m "$ANDROID_HOME" 2>/dev/null || echo "$ANDROID_HOME")" > local.properties
    echo "wrote local.properties -> $ANDROID_HOME"
fi

./gradlew "${@:-test assembleDebug}"

if [ -f app/build/outputs/apk/debug/app-debug.apk ]; then
    echo
    echo "APK: $(pwd)/app/build/outputs/apk/debug/app-debug.apk"
    echo "Install on a connected phone with:"
    echo "  \$ANDROID_HOME/platform-tools/adb install -r app/build/outputs/apk/debug/app-debug.apk"
fi
