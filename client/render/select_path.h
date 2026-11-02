#pragma once
// The select camera's recorded paths, as the 1298 client plays them (binary,
// specs/KO-FINDINGS.md 8.4): front-end.bin's path turn mode (version 7,
// content/front-end.md). A path is an .n3camera's eye and at keys; the camera
// plays one from its first frame, 30 frames a second, and stays on its last
// frame, where the turn has arrived. Kept free of GL so tests/front_end.cpp
// can run it; render/front_end.h moves the camera with it.
#include "assets/assets.h"
#include <algorithm>
#include <optional>
#include <vector>

namespace n3e::front {

// CN3Transform's frames: its tick (0043b5a0, given FLT_MIN) adds
// 30 / s_fFrmPerSec (006a3c48 30.0 over 006d3aac) a tick, 30 a second.
inline constexpr float kPathFrameRate = 30.f;

// The path's last frame, m_fFrmWhole (0043b480): the longest of its key
// sets' count x rate x 1/30 (006a3c44, 0.033333335).
inline float path_frames(const FrontPath &p) {
  constexpr float third = 1.f / 30.f;
  return std::max(float(p.eye.size()) * p.eye_rate * third, float(p.at.size()) * p.at_rate * third);
}

// One key set at `frame`, as CN3AnimKey::DataGet gives a vector (1298: the eye
// in 0043b710, the at in 004396c0): key i = trunc(frame x rate / 30); past the
// count nothing (the value stays as it was); at the count the last key; below
// it key i blended toward key i + 1 by the frame's fraction of a key, the
// last key blending toward itself (the load copies it once past the end).
inline std::optional<V> path_key(const std::vector<V> &keys, float rate, float frame) {
  const int n = int(keys.size());
  if (n == 0) return std::nullopt;
  const float step = kPathFrameRate / rate;
  const int i = int(frame * (rate / kPathFrameRate));
  if (i < 0 || i > n) return std::nullopt;
  if (i == n) return keys[size_t(n - 1)];
  const float t = (frame - float(i) * step) / step;
  const V &a = keys[size_t(i)];
  if (t == 0) return a;
  const V &b = keys[size_t(std::min(i + 1, n - 1))];
  const float u = 1.f - t;
  return V{b[0] * t + a[0] * u, b[1] * t + a[1] * u, b[2] * t + a[2] * u};
}

// The select camera on its path (1298: the proc's camera +0x1a4, a CN3Camera
// whose frame +0x110 runs to +0x10c and stays there, the clamp flag +0x114
// that 005fa670 sets after each load).
struct PathCamera {
  const FrontPath *path = nullptr;
  float frame = 0, whole = 0;
  V eye{}, at{};
  bool loaded = false;  // started since the last tick

  // 005fa670: load the path (frame 0) and tick it once at once.
  void start(const FrontPath &p) {
    path = &p;
    frame = 0;
    whole = path_frames(p);
    loaded = true;
    sample();
  }
  // On the path's last frame, as the ENTER and ESC skips leave it (005fe280,
  // the tick 005faf10: +0x110 = +0x10c) and as a turn arrives.
  void finish() {
    frame = whole;
    loaded = false;
    sample();
  }
  // The arrival test of 005fe5b0 (cases 1, 2 and 6): the frame equals the last.
  bool ended() const { return path && frame == whole; }
  // The tick's own camera tick (005faf10's last call, 0043b5a0 with
  // FLT_MIN): a tick's frames, at least 0, at most the last; then the eye
  // and at from their keys (0043b710, 004396c0). A path started since the
  // last tick takes two steps, its load's and the tick's.
  void tick(float dt) {
    if (!path) return;
    for (int k = loaded ? 2 : 1; k-- > 0;) {
      frame += kPathFrameRate * dt;
      if (frame < 0) frame = 0;
      if (whole <= frame) frame = whole;
    }
    loaded = false;
    sample();
  }
  void sample() {
    if (const auto e = path_key(path->eye, path->eye_rate, frame)) eye = *e;
    if (const auto a = path_key(path->at, path->at_rate, frame)) at = *a;
  }
};

}  // namespace n3e::front
