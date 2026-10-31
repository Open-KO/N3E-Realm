#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
base="${N3E_TOOLS:-$PWD/.cache/tools}"
mkdir -p "$base"
python -m venv "$base/venv"
"$base/venv/bin/pip" install cmake==3.31.6 black==25.1.0
if ! test -x "$base/cargo/bin/rustup"; then
  curl --proto '=https' --tlsv1.2 -fsS https://sh.rustup.rs -o "$base/rustup.sh"
  CARGO_HOME="$base/cargo" RUSTUP_HOME="$base/rustup" sh "$base/rustup.sh" -y --no-modify-path --profile minimal --default-toolchain 1.85.1
fi
CARGO_HOME="$base/cargo" RUSTUP_HOME="$base/rustup" "$base/cargo/bin/rustup" component add rustfmt --toolchain 1.85.1
if ! test -d "$base/imgui"; then
  git clone --branch v1.91.9b --depth 1 https://github.com/ocornut/imgui.git "$base/imgui"
fi
test "$(git -C "$base/imgui" rev-parse HEAD)" = f5befd2d29e66809cd1110a152e375a7f1981f06
