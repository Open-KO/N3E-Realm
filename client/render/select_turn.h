#pragma once
// The select hall's camera turn, as the 1097 client's CGameProcCharacterSelect
// turns it (binary, specs/KO-FINDINGS.md 8.2): the eye turns about the
// vertical through the camera's `at` by 1.2 rad a second, a check before each
// step; the turn ends at the slot's eye. Kept free of GL so tests/front_end.cpp
// can run it.
#include "assets/assets.h"
#include <cmath>

namespace n3e::front {

// RotateLeft/RotateRight: RotationY(s_fSecPerFrm * +-1.2) on the eye's offset
// from `at` (0043e4e0, 0043e880; 0058cd90 1.2, 0058cd94 -1.2).
inline constexpr float kSelectTurnRate = 1.2f;

// The turn, in radians about +y through `at`, that takes the camera's own eye
// `home` to `eye`: 0 for `home` itself, positive towards KO's left (+x, where
// RotateLeft takes the eye). The slots lie within a quarter turn of `home`, so
// this never wraps.
inline float select_turn(const V &home, const V &at, const V &eye) {
  const float hx = home[0] - at[0], hz = home[2] - at[2], ex = eye[0] - at[0], ez = eye[2] - at[2];
  return std::atan2(hx * ez - hz * ex, hx * ex + hz * ez);
}

// `home` turned by `angle` about the vertical through `at` (engine space,
// z reflected from KO's: RotationY(angle) there).
inline V select_eye(const V &home, const V &at, float angle) {
  const float c = std::cos(angle), s = std::sin(angle), x = home[0] - at[0], z = home[2] - at[2];
  return {at[0] + x * c - z * s, home[1], at[2] + x * s + z * c};
}

// One tick of the turn (CheckJobState 0043e4e0 in state 1) from the slot at
// `from` to the slot at `goal`, both select_turn angles: it checks, then turns.
// Towards a side slot (CheckRotateLeft/Right, 0043dc50, 0043dfb0) the turn has
// ended once the angle is past the slot's (the package cooks the slot's eye
// where KO's check ends it), and the eye stays where the last step left it.
// Back to the camera's own eye (the inline checks: the eye's x past 0) it has
// ended once the angle reaches or passes 0, and the eye is put back on `home`.
// Returns true on the tick the turn ends, which does not move the eye.
inline bool select_turn_tick(float &angle, float from, float goal, float dt) {
  const float dir = goal > from ? 1.f : -1.f, past = (angle - goal) * dir;
  if (goal == 0 ? past >= 0 : past > 0) {
    if (goal == 0) angle = 0;
    return true;
  }
  angle += dir * kSelectTurnRate * dt;
  return false;
}

}  // namespace n3e::front
