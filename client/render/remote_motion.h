#pragma once
#include "assets/assets.h"
#include "wire.pb.h"
#include <algorithm>

// Full baselines contain only currently visible instances. Never interpolate
// across a session, a missing instance, a life transition or a stalled stream.
inline n3e::V remote_position(const n3e::World &previous,
                              const n3e::World &current,
                              const n3e::Entity &entity, double age) {
  n3e::V position{entity.x(), entity.y(), entity.z()};
  if (previous.session() != current.session() ||
      current.tick() <= previous.tick() || current.tick() - previous.tick() > 4)
    return position;
  for (const auto &before : previous.entities()) {
    if (before.id() != entity.id())
      continue;
    if (before.life_state() != entity.life_state() ||
        bool(before.health()) != bool(entity.health()))
      return position;
    float blend = std::clamp(float(age / .1), 0.f, 1.f);
    return {before.x() + (entity.x() - before.x()) * blend,
            before.y() + (entity.y() - before.y()) * blend,
            before.z() + (entity.z() - before.z()) * blend};
  }
  return position;
}
