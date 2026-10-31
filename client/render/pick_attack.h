#pragma once
// Mouse actor picking, Ctrl+click and double-click attacks (PQ-011, PQ-146). KO
// client KnightOnLine.exe; addresses are the binary evidence for each rule,
// recorded in docs/implementation/evidence/pq-011-pick-set.md and
// pq-146-pick-geometry.md.
#include "assets/assets.h"
#include "network/world.h"
#include "render/targeting.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <vector>
namespace n3e::targeting {
// Pick set (005e16f0 -> 00472ab0 -> 004724c0): the NPC map +0x28 and the
// other-player map +0x38, with no state, hostility or party test. Party members
// count; the local player is not in either map. A slain NPC counts while it is
// dying and leaves at the end of its dying clip, when the manager tick moves it
// to the corpse map (00470b25-00470b9c; `Corpses`, PQ-172, PQ-199). Another
// player stays in any state until user-out (005cd1b0) or opcode 0x4e moves it
// (004723f0), so a slain player stays pickable here too. Corpses are a
// separate pick that runs only when no actor was hit (00471990 -> 005c7c60,
// which opens the corpse's bundle within 10 m). n3e's counterpart is the
// bundle model's pick (loot_visual.h); the corpse body itself is not picked
// (PQ-201), so a click on it away from that model walks.
inline bool pickable(const WorldState &w, const Corpses &corpses, const Entity &e) {
  return e.id() != w.world.self() && !corpses.contains(e.id());
}
// The attack predicate's hostility test (00468750 -> 006164c0). n3e has no
// player-versus-player rules, so its hostile actors are the living NPCs.
inline bool attackable(const Entity &e) { return e.npc() && e.health(); }
// --- Pick geometry (PQ-146, D-138; evidence pq-146-pick-geometry.md) ---
namespace pick_geometry {
inline V sub(V a, V b) { return {a[0] - b[0], a[1] - b[1], a[2] - b[2]}; }
inline float dot(V a, V b) { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }
inline V cross(V a, V b) { return {a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]}; }
} // namespace pick_geometry
// KO's ray/triangle test (004495c0 per triangle; 004288d0 is the same): front
// faces only, (e1 x e2) . d <= -1e-4 (006a3c70), determinant >= 1e-4
// (006a3c6c), barycentric bounds, and the hit at t >= 0. `d` need not be unit.
inline bool ray_triangle(V o, V d, V a, V b, V c) {
  using namespace pick_geometry;
  V e1 = sub(b, a), e2 = sub(c, a);
  if (dot(cross(e1, e2), d) > -1e-4f) return false;
  V p = cross(d, e2);
  float det = dot(e1, p);
  if (det < 1e-4f) return false;
  V t = sub(o, a);
  float u = dot(t, p);
  if (u < 0 || u > det) return false;
  V q = cross(t, e1);
  float v = dot(d, q);
  if (v < 0 || u + v > det) return false;
  return dot(e2, q) / det >= 0;
}
// KO's collision box (004482c0): eight corners from the minimum and maximum and
// twelve triangles wound outward, in KO's order.
inline constexpr std::array<uint8_t, 36> box_triangles{0, 1, 2, 0, 2, 3, 1, 4, 7, 1, 7, 2, 4, 5, 6, 4, 6, 7,
                                                       5, 0, 3, 5, 3, 6, 5, 4, 1, 5, 1, 0, 3, 2, 7, 3, 7, 6};
inline std::array<V, 8> box_corners(V lo, V hi) {
  return {{{lo[0], hi[1], lo[2]}, {hi[0], hi[1], lo[2]}, {hi[0], lo[1], lo[2]}, {lo[0], lo[1], lo[2]},
           {hi[0], hi[1], hi[2]}, {lo[0], hi[1], hi[2]}, {lo[0], lo[1], hi[2]}, {hi[0], lo[1], hi[2]}}};
}
// The box of a set of model-space points (KO 0041c300 over the joint positions):
// each axis shorter than the policy's minimum grows by its padding on each side.
struct Box { V lo{}, hi{}; };
inline Box bounds(const std::vector<V> &points, const PickPolicy &policy) {
  Box b{{0, 0, 0}, {0, 0, 0}};
  if (points.empty()) return b;
  b.lo = b.hi = points.front();
  for (const auto &p : points)
    for (int k = 0; k < 3; ++k) b.lo[k] = std::min(b.lo[k], p[k]), b.hi[k] = std::max(b.hi[k], p[k]);
  for (int k = 0; k < 3; ++k)
    if (b.hi[k] - b.lo[k] < policy.min_extent) b.hi[k] += policy.pad, b.lo[k] -= policy.pad;
  return b;
}
// An actor model's box in a pose: its joint positions (scaled model space) under
// a joint policy (KO, 0041b000 -> 0041c300), else, or when the model has no
// skeleton, its skinned vertices (the engine default).
inline Box model_box(const Scene &s, const std::vector<Node> &pose, const PickPolicy &policy) {
  std::vector<V> points;
  if (policy.joints)
    for (unsigned j = 0; j < s.joints.size(); ++j) points.push_back(s.joint_position(pose, j));
  if (points.empty()) {
    auto skinned = s.skin(pose);
    for (size_t i = 0; i < s.indices.size(); ++i) points.push_back({skinned[i * 8], skinned[i * 8 + 1], skinned[i * 8 + 2]});
  }
  return bounds(points, policy);
}
// Place a model-space box as the viewer draws the model: scaled, turned by
// `heading` and moved to `position` (x' = x cos + z sin, z' = z cos - x sin).
inline std::array<V, 8> place(const Box &b, V position, float heading, float scale = 1) {
  auto corners = box_corners(b.lo, b.hi);
  float c = std::cos(heading), s = std::sin(heading);
  for (auto &p : corners) {
    V q{p[0] * scale, p[1] * scale, p[2] * scale};
    p = {position[0] + q[0] * c + q[2] * s, position[1] + q[1], position[2] - q[0] * s + q[2] * c};
  }
  return corners;
}
inline bool ray_box(V o, V d, const std::array<V, 8> &corners) {
  for (size_t i = 0; i < box_triangles.size(); i += 3)
    if (ray_triangle(o, d, corners[box_triangles[i]], corners[box_triangles[i + 1]], corners[box_triangles[i + 2]]))
      return true;
  return false;
}
// One drawn actor, recorded while the frame is drawn: its position (the sort
// key), its character LOD (0-3; KO 004724c0 skips any other), its box in world
// space and the world-space triangle soup it was drawn with (positions are the
// first three floats of each `stride`-float vertex in frame buffer `buffer`).
struct MeshRange { unsigned buffer = 0; size_t first = 0, vertices = 0, stride = 8; };
struct PickVolume {
  uint64_t id = 0;
  V position{};
  int lod = 0;
  std::array<V, 8> box{};
  MeshRange mesh;
};
struct PickFrame {
  // 0 world and NPCs, 1 players, 2 detailed characters, 3 NPCs drawn with a
  // looks model (PQ-253).
  std::array<std::vector<float>, 4> buffers;
  std::vector<PickVolume> volumes;
  // NPCs whose death presentation had finished when the frame was drawn
  // (targeting.h); the actor pick and B skip them.
  Corpses corpses;
};
inline bool ray_mesh(V o, V d, const PickFrame &f, const MeshRange &m) {
  if (m.buffer >= f.buffers.size() || m.stride < 3) return false;
  const auto &b = f.buffers[m.buffer];
  if (m.first + m.vertices * m.stride > b.size()) return false;
  auto at = [&](size_t i) { const float *p = &b[m.first + i * m.stride]; return V{p[0], p[1], p[2]}; };
  for (size_t i = 0; i + 2 < m.vertices; i += 3)
    if (ray_triangle(o, d, at(i), at(i + 1), at(i + 2))) return true;
  return false;
}
// Screen pick (00472ab0 -> 004724c0). The ray starts at the camera eye with
// direction `dir` (Orbit::ray). Every pickable actor drawn last frame at LOD 0-3
// whose box the ray hits is a candidate, in order of distance from the eye to
// the actor's position (00472250). The only candidate wins. With several, the
// first wins whose drawn triangles the ray hits at LOD `mesh_lod` or finer, or
// at a coarser LOD at once, as its box was hit (0041c630 -> 0041c7d0: LOD 0-1
// mesh, 2-3 box). KO passes the world ray to character-local triangles there,
// so its LOD 0-1 test never accepts a near actor; n3e tests both in world space
// (correction record, D-138). No candidate accepted: 0.
inline uint64_t pick(const WorldState &w, const PickFrame &f, V eye, V dir, uint32_t mesh_lod) {
  std::vector<const PickVolume *> order;
  for (const auto &v : f.volumes) {
    if (v.lod < 0 || v.lod > 3) continue;
    for (const auto &e : w.world.entities())
      if (e.id() == v.id && pickable(w, f.corpses, e)) order.push_back(&v);
  }
  auto distance = [&](const PickVolume *v) { auto d = pick_geometry::sub(v->position, eye); return pick_geometry::dot(d, d); };
  std::stable_sort(order.begin(), order.end(), [&](auto a, auto b) { return distance(a) < distance(b); });
  std::vector<const PickVolume *> hits;
  for (auto *v : order)
    if (ray_box(eye, dir, v->box)) hits.push_back(v);
  if (hits.size() == 1) return hits.front()->id;
  for (auto *v : hits)
    if (v->lod > int(mesh_lod) || ray_mesh(eye, dir, f, v->mesh)) return v->id;
  return 0;
}
inline const PickVolume *volume(const PickFrame &f, uint64_t id) {
  for (const auto &v : f.volumes)
    if (v.id == id) return &v;
  return nullptr;
}
// A point to aim at an actor's box: its centre (test replays).
inline V box_centre(const std::array<V, 8> &corners) {
  V c{};
  for (const auto &p : corners)
    for (int k = 0; k < 3; ++k) c[k] += p[k] / 8;
  return c;
}
// Attack predicate 00468750(player, target, 0): the target is attackable and
// within reach on the ground plane, (dx, dz) only. Reach is the melee range,
// (own radius + target radius) * 0.5 + weapon range (00468620), which n3e's
// MeleeConfig::range() already models. The client's flicker test (player
// +0x330 == 1.0 after a revival) has no n3e counterpart.
inline bool can_attack(bool attackable, V self, V victim, float range) {
  return attackable && std::hypot(victim[0] - self[0], victim[2] - self[2]) <= range;
}
enum class Click { none, attack, approach };
// Ctrl+left press on an actor, camera mode 3 (005e16f0): attack when the
// predicate holds (after stopping any approach), otherwise walk to the actor
// (00465950 chase). Nothing picked: the ordinary click (walk, loot) runs.
inline Click ctrl_click(bool picked, bool predicate) {
  if (!picked) return Click::none;
  return predicate ? Click::attack : Click::approach;
}
// Left double click, camera mode 3 (005e1490): acts on the current target, not
// on a new pick. Attack when the predicate holds; otherwise approach only when
// the target is farther than the reach in 3-D; otherwise nothing.
inline Click double_click(bool has_target, bool predicate, V self, V victim, float range) {
  if (!has_target) return Click::none;
  if (predicate) return Click::attack;
  float dx = victim[0] - self[0], dy = victim[1] - self[1], dz = victim[2] - self[2];
  return std::sqrt(dx * dx + dy * dy + dz * dz) > range ? Click::approach : Click::none;
}
// Double-click detection (input tick 00640140): a left release counts as the
// second click when it comes within the system double-click time of the
// previous left release (GetDoubleClickTime; 500 ms is the Windows default and
// SDL's) and less than 6 px from it on each axis. Every left release updates
// the reference, so a third quick release counts again.
struct DoubleClick {
  uint64_t last_ms = 0;
  float last_x = 0, last_y = 0;
  bool seen = false;
  static constexpr uint64_t window_ms = 500;
  static constexpr float slop = 6;
  bool release(uint64_t now_ms, float x, float y) {
    bool doubled = seen && now_ms < last_ms + window_ms && std::abs(x - last_x) < slop && std::abs(y - last_y) < slop;
    seen = true, last_ms = now_ms, last_x = x, last_y = y;
    return doubled;
  }
};
} // namespace n3e::targeting
