#pragma once
#include "assets/assets.h"
#include <algorithm>
#include <cmath>
#include <limits>

namespace camera_geometry {
using n3e::V;
inline V sub(V a, V b) { return {a[0] - b[0], a[1] - b[1], a[2] - b[2]}; }
inline float dot(V a, V b) { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }
inline V cross(V a, V b) {
  return {a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2],
          a[0] * b[1] - a[1] * b[0]};
}
inline V unit(V v) {
  float length = std::sqrt(dot(v, v));
  for (auto &x : v)
    x /= length;
  return v;
}
// Clip a segment against a triangle's expanded prism. It conservatively
// contains the rounded triangle (sphere sweep): corners can retract early,
// never tunnel. Five planes per triangle, independent of boom length/FPS.
inline float hit(V start, V delta, V a, V b, V c, float radius) {
  V n = unit(cross(sub(b, a), sub(c, a)));
  float lo = 0, hi = 1;
  auto plane = [&](V normal, V point, float padding) {
    float distance = dot(normal, sub(start, point)) - padding;
    float speed = dot(normal, delta);
    if (std::abs(speed) < 1e-8f)
      return distance <= 0;
    float t = -distance / speed;
    if (speed < 0)
      lo = std::max(lo, t);
    else
      hi = std::min(hi, t);
    return lo <= hi;
  };
  if (!plane(n, a, radius) || !plane({-n[0], -n[1], -n[2]}, a, radius))
    return std::numeric_limits<float>::infinity();
  V vertices[] = {a, b, c, a};
  for (int i = 0; i < 3; ++i)
    if (!plane(unit(cross(sub(vertices[i + 1], vertices[i]), n)), vertices[i],
               radius))
      return std::numeric_limits<float>::infinity();
  return lo;
}
} // namespace camera_geometry

// When the camera keys and screen edges may act (PQ-012, D-143; KO 005c6990).
namespace camera_input {
struct Context {
  bool in_world = false;        // in play, including while a text field has focus
  bool typing = false;          // a text field has focus (KO DAT_006dfe20)
  bool window_focused = false;
  bool mouse_in_window = false; // the window has the mouse focus
  bool dragging = false;        // a right-drag holds the cursor (relative mode)
  bool tools_keyboard = false, tools_mouse = false;  // tools build UI capture
};
// Home/End: KO skips them while a text field has focus.
inline bool pitch_keys(const Context &c) {
  return c.in_world && !c.typing && c.window_focused && !c.tools_keyboard;
}
// Edge yaw: KO has no text-focus or player-state test; n3e needs the cursor
// in the focused window. During a right-drag n3e does not turn at all, a
// recorded gap (D-143, PQ-160): KO's edge test reads that frame's raw cursor
// (005c6990), so frames on which the cursor rests on a border column still
// turn there; once a moving frame puts the cursor back (005e3e20, 006400f0's
// clamp) it is probably off the column (inference).
inline bool edge(const Context &c) {
  return c.in_world && c.window_focused && c.mouse_in_window && !c.dragging &&
         !c.tools_mouse;
}
} // namespace camera_input

// Projection, picking, LOD and obstruction share one package projection.
struct Orbit {
  n3e::CameraConfig config;
  float yaw = 0, pitch, distance, boom = 0;
  n3e::V eye{}, right{}, up{}, back{}, focus{};
  explicit Orbit(n3e::CameraConfig c = {})
      : config(c), pitch(c.pitch), distance(c.distance) {}
  // Right-drag by logical pixels. Horizontal yaws; vertical pitches, or with
  // the N3V2 distance axis moves the camera away as the cursor moves down (KO
  // mode 3, 005e3e20 -> 0063e2e0). Fixed per-pixel rates (D-143 correction).
  void drag(float x, float y) {
    if (!std::isfinite(x) || !std::isfinite(y))
      return;
    yaw = std::remainder(yaw - x * config.yaw_per_pixel, 6.2831853f);
    if (config.drag_distance)
      distance = std::clamp(distance + y * config.distance_per_pixel,
                            config.distance_min, config.distance_max);
    else
      pitch = std::clamp(pitch + y * config.pitch_per_pixel, config.pitch_min,
                         config.pitch_max);
  }
  // Held pitch keys for dt seconds: +1 raises the eye, -1 lowers it; +1 wins
  // when both are held (KO 005c6990 tests Home before End; 0063e0e0 clamps).
  void key_pitch(bool raise, bool lower, float dt) {
    if (!std::isfinite(dt) || dt <= 0 || (!raise && !lower))
      return;
    pitch = std::clamp(pitch + (raise ? 1 : -1) * config.key_pitch_rate * dt,
                       config.pitch_min, config.pitch_max);
  }
  // The cursor on the outermost column of a window w logical pixels wide turns
  // the camera for dt seconds, the left edge as a drag to the left (KO
  // 005c6990: x == 0 or x == W - 1, 2 rad/s in mode 3; a cursor outside the
  // window matches neither). Returns the direction.
  static int edge(float x, float w) {
    if (!std::isfinite(x) || !(w >= 2))
      return 0;
    return x >= 0 && x < 1 ? -1 : x >= w - 1 && x < w ? 1 : 0;
  }
  void edge_yaw(int direction, float dt) {
    if (!std::isfinite(dt) || dt <= 0 || !direction)
      return;
    yaw = std::remainder(yaw - direction * config.edge_yaw_rate * dt, 6.2831853f);
  }
  void zoom(float steps) {
    if (std::isfinite(steps))
      distance = std::clamp(distance - steps * config.zoom_per_step,
                            config.distance_min, config.distance_max);
  }
  void update(n3e::V position, const n3e::Scene &scene, float height = 1.6f,
              float aspect = 1) {
    focus = position;
    focus[1] += config.focus_height + config.focus_scale * height;
    right = {std::cos(yaw), 0, -std::sin(yaw)};
    back = {std::sin(yaw) * std::cos(pitch), std::sin(pitch),
            std::cos(yaw) * std::cos(pitch)};
    up = {-std::sin(yaw) * std::sin(pitch), std::cos(pitch),
          -std::cos(yaw) * std::sin(pitch)};
    n3e::V delta{back[0] * distance, back[1] * distance, back[2] * distance};
    // Enclose the configured near-plane corners, including wide windows.
    float radius = std::max(config.clearance,
                            config.near_plane * std::sqrt(1 + (aspect * aspect + 1) * (std::tan(config.fov/2)*std::tan(config.fov/2))));
    float fraction = 1;
    // Only triangles near the swept segment can obstruct it (PQ-215). hit()
    // pads each edge slab by the radius, which reaches past the radius at an
    // acute corner, so the gather adds a metre beyond it.
    const auto near = scene.collision.segment(focus, delta, radius + 1.f);
    for (size_t i = 0; i < near.size(); i += 3)
      fraction = std::min(fraction,
                          camera_geometry::hit(focus, delta, near[i], near[i + 1],
                                               near[i + 2], radius));
    boom = std::max(0.f, distance * fraction - (fraction < 1 ? .001f : 0.f));
    for (int k = 0; k < 3; ++k)
      eye[k] = focus[k] + back[k] * boom;
  }
  bool ground_point(float x, float y, int w, int h, const n3e::Scene &scene,
                    n3e::V &result) const {
    if (w <= 0 || h <= 0 || !std::isfinite(x) || !std::isfinite(y))
      return false;
    n3e::V ray{};
    for (int k = 0; k < 3; ++k)
      ray[k] = -back[k] + right[k] * (x - w * .5f) / (h * (.5f/std::tan(config.fov/2))) +
               up[k] * (h * .5f - y) / (h * (.5f/std::tan(config.fov/2)));
    ray = camera_geometry::unit(ray);
    for (auto &v : ray)
      v *= 100;
    float nearest = 1;
    bool walkable = false;
    const auto near = scene.collision.segment(eye, ray, 0);
    for (size_t i = 0; i < near.size(); i += 3) {
      auto a = near[i], b = near[i + 1], c = near[i + 2];
      float t = camera_geometry::hit(eye, ray, a, b, c, 0);
      if (t >= 0 && t < nearest) {
        nearest = t;
        auto n = camera_geometry::unit(camera_geometry::cross(
            camera_geometry::sub(b, a), camera_geometry::sub(c, a)));
        walkable = std::abs(n[1]) >= .7071067f;
      }
    }
    if (!walkable)
      return false; // A foreground wall occludes ground behind it.
    for (int k = 0; k < 3; ++k)
      result[k] = eye[k] + ray[k] * nearest;
    return true;
  }
  // The cursor ray's direction from the eye, unnormalized with unit depth along
  // the view axis: the inverse of project(). KO builds its pick ray the same way
  // (004724c0: view-space (sx/P11, sy/P22, 1) through the inverse view matrix).
  n3e::V ray(float x, float y, int w, int h) const {
    float f = h * (.5f / std::tan(config.fov / 2));
    n3e::V d{};
    for (int k = 0; k < 3; ++k)
      d[k] = -back[k] + right[k] * (x - w * .5f) / f + up[k] * (h * .5f - y) / f;
    return d;
  }
  n3e::V project(n3e::V p, int w, int h) const {
    p = camera_geometry::sub(p, eye);
    float depth = -camera_geometry::dot(back, p);
    return {w * .5f + camera_geometry::dot(right, p) * h * (.5f/std::tan(config.fov/2)) / depth,
            h * .5f - camera_geometry::dot(up, p) * h * (.5f/std::tan(config.fov/2)) / depth,
            depth};
  }
};
