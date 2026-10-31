#pragma once
#include <cstdint>

// The HUD target bar's fill (PQ-249): an NPC spawned from an N3N3 template
// carries its own maximum health (Entity.max_health, wire 30); any other target
// keeps the package's NPC health as the maximum. Server values only.
inline float target_health_fraction(uint32_t health, uint32_t max_health, float package_max) {
  const float maximum = max_health ? float(max_health) : package_max;
  return maximum > 0.f ? float(health) / maximum : 0.f;
}
