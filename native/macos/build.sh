#!/bin/zsh
set -eu
build_source="${0:A:h}"
app_bundle="${1:?Usage: native/macos/build.sh /absolute/path/LabSkill.app}"
if [[ "$app_bundle" != /* || -e "$app_bundle" ]]; then
  print -u2 'Choose an absolute output path that does not exist.'
  exit 1
fi
build_work="$(mktemp -d "${TMPDIR:-/tmp}/labskill-native.XXXXXX")"
trap 'rm -rf -- "$build_work"' EXIT
mkdir -p "$app_bundle/Contents/MacOS" "$app_bundle/Contents/Resources" "$build_work/iconset.iconset"
/usr/bin/swiftc -O -framework AppKit -module-cache-path "$build_work/cache" \
  "$build_source/Icon.swift" -o "$build_work/icon-generator"
"$build_work/icon-generator" "$build_work/iconset.iconset"
/usr/bin/iconutil -c icns "$build_work/iconset.iconset" -o "$app_bundle/Contents/Resources/LabSkill.icns"
/usr/bin/swiftc -O -framework AppKit -framework WebKit -target arm64-apple-macosx12.0 \
  -module-cache-path "$build_work/cache" \
  "$build_source/LauncherPaths.swift" "$build_source/Launcher.swift" \
  -o "$app_bundle/Contents/MacOS/LabSkill"
/usr/bin/python3 - "$app_bundle" <<'PY'
import plistlib
import sys
from pathlib import Path

contents = Path(sys.argv[1]) / "Contents"
metadata = {
    "CFBundleDevelopmentRegion": "ko",
    "CFBundleDisplayName": "LabSkill",
    "CFBundleExecutable": "LabSkill",
    "CFBundleIconFile": "LabSkill.icns",
    "CFBundleIdentifier": "local.labskill.catalog",
    "CFBundleInfoDictionaryVersion": "6.0",
    "CFBundleName": "LabSkill",
    "CFBundlePackageType": "APPL",
    "CFBundleShortVersionString": "0.2.0",
    "CFBundleVersion": "1",
    "LSMinimumSystemVersion": "12.0",
    "NSHighResolutionCapable": True,
    "NSPrincipalClass": "NSApplication",
    "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True},
}
(contents / "Info.plist").write_bytes(plistlib.dumps(metadata))
(contents / "PkgInfo").write_bytes(b"APPL????")
PY
/usr/bin/codesign --force --sign - "$app_bundle"
print 'Built Apple Silicon launcher. Python is external; this is ad-hoc signed, not notarized.'
