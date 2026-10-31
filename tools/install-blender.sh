#!/usr/bin/env bash
# Install the pinned portable Blender into .cache/tools/blender (no root, no system
# packages). Used headless by tools/assetc/character_import.py.
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION=5.2.2
SHA256=84098912789dc450e95697c4184fb8a90acbe5111c2ba4aede3fecb57806a168
TOOLS="${N3E_TOOLS:-$PWD/.cache/tools}"
ARCHIVE="blender-$VERSION-linux-x64.tar.xz"
if "$TOOLS/blender/blender" --version 2>/dev/null | grep -q "Blender $VERSION"; then
  echo "Blender $VERSION already installed"; exit 0
fi
mkdir -p "$TOOLS"
curl -fL -o "$TOOLS/$ARCHIVE" "https://download.blender.org/release/Blender${VERSION%.*}/$ARCHIVE"
echo "$SHA256  $TOOLS/$ARCHIVE" | sha256sum -c -
tar -xf "$TOOLS/$ARCHIVE" -C "$TOOLS"
ln -sfn "blender-$VERSION-linux-x64" "$TOOLS/blender"
rm "$TOOLS/$ARCHIVE"
"$TOOLS/blender/blender" --version | head -1
