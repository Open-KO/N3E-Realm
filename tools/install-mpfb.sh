#!/usr/bin/env bash
# Install MPFB2 and the CC0 MakeHuman system assets into the project-local Blender
# profile (.cache/tools/blender-user), used by tools/assetc/blender/mpfb_investigator.py.
# The user's own Blender settings are never touched.
set -euo pipefail
cd "$(dirname "$0")/.."
./tools/install-blender.sh
TOOLS="${N3E_TOOLS:-$PWD/.cache/tools}"
export BLENDER_USER_RESOURCES="$TOOLS/blender-user"
MPFB_SHA=4f0a879d64a39bf646fbf5f53601ac678855da329d650617dca5737548239a87
ASSETS_SHA=b542127a8e25547c7c29c19f2d1d2adb9a664c80396ecd694095dbc8028a0107
DATA="$BLENDER_USER_RESOURCES/extensions/.user/user_default/mpfb/data"
if ! test -d "$BLENDER_USER_RESOURCES/extensions/user_default/mpfb"; then
  curl -fsSL -o "$TOOLS/mpfb-v2.0.17.zip" \
    "https://extensions.blender.org/download/sha256:$MPFB_SHA/add-on-mpfb-v2.0.17.zip?repository=%2Fapi%2Fv1%2Fextensions%2F&blender_version_min=4.2.0"
  echo "$MPFB_SHA  $TOOLS/mpfb-v2.0.17.zip" | sha256sum -c -
  "$TOOLS/blender/blender" -b --factory-startup --command extension install-file -r user_default -e "$TOOLS/mpfb-v2.0.17.zip"
fi
if ! test -d "$DATA/proxymeshes/proxy741"; then
  curl -fsSL -o "$TOOLS/makehuman_system_assets_cc0.zip" \
    https://files2.makehumancommunity.org/asset_packs/makehuman_system_assets/makehuman_system_assets_cc0.zip
  # The publisher lists no checksum; this is the hash of the pack verified on 2026-09-25.
  echo "$ASSETS_SHA  $TOOLS/makehuman_system_assets_cc0.zip" | sha256sum -c -
  mkdir -p "$DATA" && unzip -q -o "$TOOLS/makehuman_system_assets_cc0.zip" -d "$DATA"
fi
echo "MPFB 2.0.17 and MakeHuman system assets ready in $BLENDER_USER_RESOURCES"
