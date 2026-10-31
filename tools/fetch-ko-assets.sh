#!/usr/bin/env bash
# Fetch the raw Knight Online client asset tree into assets/ko/ (git-ignored).
#
# The tree is a pinned, immutable build input (specs/10-content.md): one .tar.zst
# whose sha256 is recorded in UPSTREAM.md and stored as a Release asset of this
# repository. Nothing from it is committed or published uncooked. Idempotent: a
# verified extract is reused; a wrong hash is deleted.
set -euo pipefail
cd "$(dirname "$0")/.."

DEST="assets/ko"
SHA=$(sed -n 's/^KO assets: *ko-client-assets-\([0-9a-f]\{64\}\)\.tar\.zst.*/\1/p' UPSTREAM.md)
URL=$(sed -n 's/^KO assets URL: *//p' UPSTREAM.md)
if [ -z "$SHA" ]; then echo "UPSTREAM.md has no 'KO assets:' pin" >&2; exit 2; fi

if [ -f "$DEST/.sha256" ] && [ "$(cat "$DEST/.sha256")" = "$SHA" ]; then
  echo "assets/ko already at $SHA"; exit 0
fi

CACHE="${N3E_KO_CACHE:-${XDG_CACHE_HOME:-$HOME/.cache}/n3e-realm}"
mkdir -p "$CACHE"
TAR="$CACHE/ko-client-assets-$SHA.tar.zst"
if [ ! -f "$TAR" ]; then
  if [ -n "${N3E_KO_TARBALL:-}" ]; then cp "$N3E_KO_TARBALL" "$TAR"
  elif [ -n "$URL" ]; then curl -fL --retry 3 -o "$TAR.part" "$URL" && mv "$TAR.part" "$TAR"
  else echo "no URL in UPSTREAM.md and N3E_KO_TARBALL unset" >&2; exit 2; fi
fi
echo "$SHA  $TAR" | sha256sum -c - >/dev/null || { rm -f "$TAR"; echo "sha256 mismatch; removed $TAR" >&2; exit 3; }

rm -rf "$DEST" "$DEST.tmp"; mkdir -p "$DEST.tmp"
zstd -dc "$TAR" | tar -x -C "$DEST.tmp"
# The tarball's root is the Client directory itself.
mv "$DEST.tmp" "$DEST"
echo "$SHA" > "$DEST/.sha256"
echo "assets/ko fetched at $SHA"
