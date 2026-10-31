#include "world.h"
#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>
namespace n3e {
static bool walkable(const V &a, const V &b, const V &c) {
  V u{b[0] - a[0], b[1] - a[1], b[2] - a[2]},
      v{c[0] - a[0], c[1] - a[1], c[2] - a[2]};
  V n{u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2],
      u[0] * v[1] - u[1] * v[0]};
  return std::abs(n[1]) >=
         .707107f * std::sqrt(n[0] * n[0] + n[1] * n[1] + n[2] * n[2]);
}
static bool allowed(const std::vector<V> &t, V old, float x, float z, V &out,
                    MovementConfig cfg = {}) {
  float y = -std::numeric_limits<float>::infinity();
  float ceiling = std::numeric_limits<float>::infinity();
  for (size_t i = 0; i < t.size(); i += 3) {
    auto a = t[i], b = t[i + 1], c = t[i + 2];
    if (!walkable(a, b, c))
      continue;
    float d = (b[2] - c[2]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[2] - c[2]);
    if (std::abs(d) < 1e-8)
      continue;
    float u = ((b[2] - c[2]) * (x - c[0]) + (c[0] - b[0]) * (z - c[2])) / d;
    float v = ((c[2] - a[2]) * (x - c[0]) + (a[0] - c[0]) * (z - c[2])) / d;
    if (u >= -1e-6 && v >= -1e-6 && u + v <= 1 + 1e-6) {
      float surface = u * a[1] + v * b[1] + (1 - u - v) * c[1];
      // A roof is not reachable support. Retain it for headroom rejection.
      if (surface <= old[1] + cfg.step_height)
        y = std::max(y, surface);
      else
        ceiling = std::min(ceiling, surface);
    }
  }
  if (!std::isfinite(y) || std::abs(y - old[1]) > cfg.step_height ||
      ceiling < y + cfg.height)
    return false;
  for (size_t i = 0; i < t.size(); i += 3) {
    if (walkable(t[i], t[i + 1], t[i + 2]))
      continue;
    float lo = std::min({t[i][1], t[i + 1][1], t[i + 2][1]}),
          hi = std::max({t[i][1], t[i + 1][1], t[i + 2][1]});
    // A reachable riser must not block the body before its centre can step up.
    if (hi <= y + cfg.step_height || lo >= y + cfg.height)
      continue;
    for (int j = 0; j < 3; ++j) {
      auto a = t[i + j], b = t[i + (j + 1) % 3];
      float dx = b[0] - a[0], dz = b[2] - a[2];
      float q = std::clamp(((x - a[0]) * dx + (z - a[2]) * dz) /
                               std::max(dx * dx + dz * dz, 1e-12f),
                           0.f, 1.f);
      if (std::pow(x - a[0] - q * dx, 2) + std::pow(z - a[2] - q * dz, 2) <
          cfg.radius * cfg.radius)
        return false;
    }
  }
  out = {x, y, z};
  return true;
}
V walk(const std::vector<V> &t, V p, float x, float z) {
  float length = std::max(1.f, std::sqrt(x * x + z * z));
  float dx = x / length * .15f, dz = z / length * .15f;
  V q;
  if (allowed(t, p, p[0] + dx, p[2] + dz, q))
    return q;
  if (allowed(t, p, p[0] + dx, p[2], q))
    p = q;
  if (allowed(t, p, p[0], p[2] + dz, q))
    p = q;
  return p;
}
V advance(const std::vector<V> &t, V p, float x, float z, uint32_t mode,
          MovementConfig cfg, float multiplier) {
  if (!cfg.valid() || !std::isfinite(x) || !std::isfinite(z) ||
      std::abs(x) > 1 || std::abs(z) > 1)
    throw std::runtime_error("invalid movement policy/input");
  if (!std::isfinite(multiplier) || multiplier < 1 || multiplier > 10)
    throw std::runtime_error("invalid movement multiplier");
  float distance = cfg.speed(mode) * multiplier * .05f;
  unsigned count =
      unsigned(std::ceil(distance / std::min(cfg.radius * .5f, .05f)));
  if(count > 61) throw std::runtime_error("movement substep budget");
  float length = std::max(1.f, std::sqrt(x * x + z * z));
  float dx = x / length * distance / count, dz = z / length * distance / count;
  for (unsigned i = 0; i < count; ++i) {
    V q;
    if (allowed(t, p, p[0] + dx, p[2] + dz, q, cfg))
      p = q;
    else {
      if (allowed(t, p, p[0] + dx, p[2], q, cfg))
        p = q;
      if (allowed(t, p, p[0], p[2] + dz, q, cfg))
        p = q;
    }
  }
  return p;
}
// Each overload gathers the triangles within its own reach (every point the
// move can visit, plus the radius) and runs the full-scan solver on them;
// Collision::near pads each triangle's bounds, so none it would use is missed.
V walk(const Collision &c, V p, float x, float z) {
  float length = std::max(1.f, std::sqrt(x * x + z * z));
  float reach = std::max(std::abs(x), std::abs(z)) / length * .15f + MovementConfig{}.radius;
  if (!std::isfinite(reach))
    return p;
  return walk(c.around(p[0], p[2], reach), p, x, z);
}
V advance(const Collision &c, V p, float x, float z, uint32_t mode, MovementConfig cfg, float multiplier) {
  if (!cfg.valid() || !std::isfinite(x) || !std::isfinite(z) || std::abs(x) > 1 || std::abs(z) > 1)
    throw std::runtime_error("invalid movement policy/input");
  if (!std::isfinite(multiplier) || multiplier < 1 || multiplier > 10)
    throw std::runtime_error("invalid movement multiplier");
  float reach = cfg.speed(mode) * multiplier * .05f + cfg.radius;
  return advance(c.around(p[0], p[2], reach), p, x, z, mode, cfg, multiplier);
}
} // namespace n3e
