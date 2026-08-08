# Building without Android Studio

The app builds from the command line with a portable JDK and the Android SDK
command-line tools. Nothing is installed system-wide, nothing needs admin
rights, and nothing touches an existing Android Studio setup.

Already set up on this machine at `~/android-toolchain`. To rebuild:

```bash
cd android && ./build.sh
```

## Recreating the toolchain elsewhere

About 1.2 GB of downloads, then roughly 500 MB more on the first build as
Gradle fetches dependencies.

```bash
mkdir -p ~/android-toolchain && cd ~/android-toolchain

curl -L -o jdk.zip "https://api.adoptium.net/v3/binary/latest/17/ga/windows/x64/jdk/hotspot/normal/eclipse"
curl -L -o cmdline-tools.zip "https://dl.google.com/android/repository/commandlinetools-win-11076708_latest.zip"

unzip -q jdk.zip
mkdir -p sdk/cmdline-tools && unzip -q cmdline-tools.zip -d sdk/cmdline-tools
mv sdk/cmdline-tools/cmdline-tools sdk/cmdline-tools/latest
```

Then accept the licences and install the SDK packages:

```bash
export JAVA_HOME=~/android-toolchain/jdk-17.0.20+8
yes | ~/android-toolchain/sdk/cmdline-tools/latest/bin/sdkmanager.bat --licenses
```

```bash
~/android-toolchain/sdk/cmdline-tools/latest/bin/sdkmanager.bat --install "platform-tools" "platforms;android-35" "build-tools;35.0.0"
```

The Gradle wrapper (`gradlew`) is committed, so no separate Gradle install is
needed — it downloads its own distribution on first run.

## Two Windows traps, both already handled

Recording these because each produced an error message that named neither the
real cause nor the file involved, and both cost real time.

### 1. `Unable to establish loopback connection`

Gradle's daemon calls `Selector.open()`, which on Windows builds an internal
pipe over an **AF_UNIX socket placed in the temp directory**. When that path
contains a space — `C:\Users\Acer Nitro 5\AppData\Local\Temp` — `connect()`
fails with `Invalid argument`, and Gradle reports only the loopback message.

TCP loopback is fine; it is specifically AF_UNIX, and specifically the path.
Confirmed by binding an AF_UNIX socket from a short path (works) and from a long
one (fails).

Fixed by pointing the socket at a short, space-free directory:

```
-Djdk.net.unixdomain.tmpdir=C:\Temp
```

Set in two places, because they cover different JVMs:

- `gradle.properties` → `org.gradle.jvmargs`, for the **daemon**
- `JAVA_TOOL_OPTIONS` in `build.sh`, for the **launcher** and every forked JVM

`org.gradle.jvmargs` alone is not enough — the launcher fails before the daemon
is ever consulted. `C:\Temp` must exist.

### 2. `The filename, directory name, or volume label syntax is incorrect`

`local.properties` is a Java `.properties` file, where **a backslash is an
escape character**. Writing

```
sdk.dir=C:\Users\Acer Nitro 5\android-toolchain\sdk
```

silently loses every separator. Use forward slashes (Java accepts them on
Windows) or double every backslash. `build.sh` writes the file correctly, and
it stays out of git because the path is machine-local.

## Build outputs

| Command | Output |
| --- | --- |
| `./build.sh test` | 6 JVM unit tests, no device needed |
| `./build.sh assembleDebug` | `app/build/outputs/apk/debug/app-debug.apk` (7.4 MB) |
| `./build.sh assembleRelease` | `app-release-unsigned.apk` (2.5 MB, R8-minified) |

The release APK is unsigned; sideloading needs a debug build or a signing
config. Both variants currently compile and pass `lintVitalRelease`.

## Installing on a phone

```bash
~/android-toolchain/sdk/platform-tools/adb.exe install -r app/build/outputs/apk/debug/app-debug.apk
```

The phone needs USB debugging enabled (Settings → About phone → tap Build
number seven times → Developer options → USB debugging).
