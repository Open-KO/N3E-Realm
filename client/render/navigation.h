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

// Where a left press or a held left button points (RQ-210).
enum class WalkPointer { world, ui, outside };

// The click-to-move walk after a left press or a held button's refresh;
// `aimed` is the world pick's result (a ground point to walk to). KO 1097's
// left-press and held-button handlers (0051bcc0, 0051c3a0) return before they
// touch the move while the UI manager's flag (+0xb4) is set, which the base
// tick (00545390) sets whenever the UI's mouse pass did anything, a window
// under the pointer included: a press or hold over a window (the inventory
// button, an open inventory) leaves the walk going to its last point. A held
// pointer outside the window stops it (n3e policy).
inline bool pointer_walk(bool walking, WalkPointer where, bool aimed) {
  return where == WalkPointer::world ? aimed
                                     : where == WalkPointer::ui && walking;
}

// Only a press that began on navigable ground owns a held cursor gesture.
// Releasing keeps the last destination; focus/keyboard cancellation and a
// pointer outside the window disarm it; over a window it only stops aiming
// (pointer_walk).
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
