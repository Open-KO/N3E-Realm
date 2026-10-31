#pragma once
#include "assets/assets.h"
#include <cmath>
#include <cstdint>

// Presentation only: never feed this position back into prediction/collision.
// A critically damped spring removes the 20 Hz steps and small reconciliation
// jumps, with roughly 67 ms of tracking lag at steady speed.
struct PlayerMotion {
  n3e::V position{}, velocity{};
  uint64_t session = 0, identity = 0;
  double last = 0;
  bool alive = false, initialized = false;
  n3e::V update(n3e::V target, double now, uint64_t new_session,
                uint64_t new_identity, bool new_alive, bool moving = true,
                bool blend_stop = false) {
    double dt = now - last;
    float distance2 = 0;
    for (int i = 0; i < 3; ++i)
      distance2 += (target[i] - position[i]) * (target[i] - position[i]);
    // Legacy immediate idle poses settle at prediction on release. With a
    // blended stop, retain the spring through that blend instead of snapping
    // the actor ahead of its camera. This never changes simulation movement.
    if ((!moving && !blend_stop) || !initialized || session != new_session ||
        identity != new_identity || alive != new_alive || dt < 0 || dt > .25 ||
        distance2 > 4) {
      position = target;
      velocity = {};
    } else {
      constexpr double omega = 30;
      double decay = std::exp(-omega * dt);
      for (int i = 0; i < 3; ++i) {
        double offset = position[i] - target[i];
        double impulse = velocity[i] + omega * offset;
        position[i] = target[i] + (offset + impulse * dt) * decay;
        velocity[i] = (velocity[i] - omega * impulse * dt) * decay;
      }
    }
    session = new_session;
    identity = new_identity;
    alive = new_alive;
    initialized = true;
    last = now;
    return position;
  }
};
