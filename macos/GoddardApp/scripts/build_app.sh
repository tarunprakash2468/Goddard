#!/usr/bin/env bash
set -e

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
APP_NAME="Goddard"
BUNDLE_ID="com.goddard.aerospace"
SWIFT_PKG_DIR="$REPO_ROOT/macos/GoddardApp"
BUILD_DIR="$REPO_ROOT/build"
APP_BUNDLE="$BUILD_DIR/$APP_NAME.app"
MACOS_DIR="$APP_BUNDLE/Contents/MacOS"
RESOURCES_DIR="$APP_BUNDLE/Contents/Resources"
INSTALL_FLAG=false

for arg in "$@"; do
  [[ "$arg" == "--install" ]] && INSTALL_FLAG=true
done

echo "🚀 Building $APP_NAME.app..."
mkdir -p "$BUILD_DIR"

# Compile Swift package
cd "$SWIFT_PKG_DIR"
swift build -c release 2>&1
BINARY_PATH=$(swift build -c release --show-bin-path 2>/dev/null)/GoddardApp

# Assemble .app bundle
mkdir -p "$MACOS_DIR" "$RESOURCES_DIR"
cp "$BINARY_PATH" "$MACOS_DIR/$APP_NAME"
chmod +x "$MACOS_DIR/$APP_NAME"

# Info.plist
cat > "$APP_BUNDLE/Contents/Info.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>$APP_NAME</string>
  <key>CFBundleDisplayName</key><string>Goddard Aerospace</string>
  <key>CFBundleIdentifier</key><string>$BUNDLE_ID</string>
  <key>CFBundleVersion</key><string>0.1.0</string>
  <key>CFBundleShortVersionString</key><string>0.1.0</string>
  <key>CFBundleExecutable</key><string>$APP_NAME</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>NSPrincipalClass</key><string>NSApplication</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>LSMinimumSystemVersion</key><string>14.0</string>
  <key>NSAppTransportSecurity</key>
  <dict>
    <key>NSAllowsArbitraryLoads</key><false/>
    <key>NSExceptionDomains</key>
    <dict>
      <key>localhost</key>
      <dict>
        <key>NSExceptionAllowsInsecureHTTPLoads</key><true/>
        <key>NSIncludesSubdomains</key><true/>
      </dict>
    </dict>
  </dict>
</dict>
</plist>
EOF

# Generate AppIcon (simple colored placeholder using sips/iconutil)
if command -v sips &> /dev/null && command -v iconutil &> /dev/null; then
  ICON_SRC="/tmp/goddard_icon_src.png"
  ICONSET="/tmp/GoddardIcon.iconset"
  python3 -c "
import struct, zlib, base64
# Minimal 1024x1024 PNG: dark aerospace blue background with 'G' glyph (placeholder)
# Generate a simple solid color PNG programmatically
def gen_png(size, r, g, b):
    raw = bytes([0] + [r,g,b,255]*size for _ in range(size)).replace(b'',b'',1)
    # Actually create a proper solid PNG
    import subprocess
    subprocess.run(['python3', '-c', f'''
import struct, zlib
def make_png(w, h, r, g, b):
    def chunk(t, d): crc = zlib.crc32(t+d); return struct.pack('>I',len(d))+t+d+struct.pack('>I',crc)
    raw = b''.join(b'\x00'+bytes([r,g,b,255]*w) for _ in range(h))
    data = chunk(b'IHDR', struct.pack('>IIBBBBB',w,h,8,2,0,0,0))
    data += chunk(b'IDAT', zlib.compress(raw))
    data += chunk(b'IEND', b'')
    with open(\"/tmp/icon1024.png\", \"wb\") as f: f.write(b\"\\x89PNG\\r\\n\\x1a\\n\" + data)
make_png({size},{size},8,20,48)
'''])
gen_png(1024, 8, 20, 48)
" 2>/dev/null || python3 -c "
import struct, zlib
def chunk(t, d): crc = zlib.crc32(t+d); return struct.pack('>I',len(d))+t+d+struct.pack('>I',crc)
w, h = 1024, 1024
raw = b''.join(b'\x00'+bytes([8,20,48,255]*w) for _ in range(h))
data = chunk(b'IHDR', struct.pack('>IIBBBBB',w,h,8,2,0,0,0))
data += chunk(b'IDAT', zlib.compress(raw))
data += chunk(b'IEND', b'')
with open('/tmp/icon1024.png', 'wb') as f: f.write(b'\x89PNG\r\n\x1a\n' + data)
"
  mkdir -p "$ICONSET"
  for size in 16 32 64 128 256 512 1024; do
    sips -z $size $size /tmp/icon1024.png --out "$ICONSET/icon_${size}x${size}.png" &>/dev/null || true
  done
  iconutil -c icns "$ICONSET" -o "$RESOURCES_DIR/AppIcon.icns" 2>/dev/null || true
  rm -rf "$ICONSET" /tmp/icon1024.png
fi

echo "✅ Built: $APP_BUNDLE"
du -sh "$APP_BUNDLE"

if [[ "$INSTALL_FLAG" == "true" ]]; then
  echo "📦 Installing to /Applications/$APP_NAME.app ..."
  rm -rf "/Applications/$APP_NAME.app"
  cp -R "$APP_BUNDLE" "/Applications/$APP_NAME.app"
  # Refresh LaunchServices
  /System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "/Applications/$APP_NAME.app" 2>/dev/null || true
  echo "✅ Installed: /Applications/$APP_NAME.app"
  echo "   Open with: open '/Applications/$APP_NAME.app'"
fi

echo "🎉 Build complete. Run with: open '$APP_BUNDLE'"
