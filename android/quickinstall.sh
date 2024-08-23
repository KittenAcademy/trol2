#!/bin/bash
# Build release target, use debug key to sign and adb to install apk
#

# Function to find the latest build-tools version
find_latest_build_tools() {
    local build_tools_dir="$1/build-tools"
    local latest_version=$(ls "$build_tools_dir" | sort -V | tail -n 1)
    echo "$latest_version"
}

# Find the Android SDK path dynamically
ANDROID_HOME=$(dirname $(dirname $(which adb)))

# Find the latest build-tools version
LATEST_BUILD_TOOLS_VERSION=$(find_latest_build_tools "$ANDROID_HOME")

# Define the paths to the build tools
ZIPALIGN="$ANDROID_HOME/build-tools/$LATEST_BUILD_TOOLS_VERSION/zipalign"
APKSIGNER="$ANDROID_HOME/build-tools/$LATEST_BUILD_TOOLS_VERSION/apksigner"
KEYSTORE="$HOME/.android/debug.keystore"

# Remove old APK
rm ./app-release-signed.apk

# Build the APK
./gradlew clean assembleRelease

# Align the APK
$ZIPALIGN -v 4 app/build/outputs/apk/release/app-release-unsigned.apk ./app-release-aligned.apk

# Sign the APK
$APKSIGNER sign --ks $KEYSTORE --ks-key-alias androiddebugkey --ks-pass pass:android --key-pass pass:android --out ./app-release-signed.apk ./app-release-aligned.apk

# Install the APK
adb install ./app-release-signed.apk

# Clean up
 ./gradlew clean
rm ./app-release-aligned.apk ./app-release-signed.apk.idsig

