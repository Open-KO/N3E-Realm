#pragma once
#include "assets/assets.h"
#include <algorithm>
#include <cmath>

// Facing-relative input; camera orientation is deliberately independent.
inline n3e::V facing_input(float &heading, int turn, int travel, double dt,
                           float turn_rate = 1.0471976f) {
  // Do not accumulate a turn burst after a suspended/minimized frame.
  if (dt >= 0 && dt <= .25)
    heading = std::remainder(heading - turn * turn_rate * dt, 6.2831853);
  return {-std::sin(heading) * travel, 0, -std::cos(heading) * travel};
}

// Only a press that began on navigable ground owns a held cursor gesture.
// Releasing keeps the last destination; UI/focus/keyboard cancellation disarms
// it.
struct HeldGround {
  bool active = false;
  double pressed = 0;
  double delay = .1;
  void begin(bool ground, double now) {
    active = ground;
    pressed = now;
  }
  void cancel() { active = false; }
  bool refresh(double now, bool allowed) {
    if (!allowed)
      active = false;
    return active && now - pressed > delay;
  }
};
