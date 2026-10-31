#pragma once
// Static collision (PQ-215): a native heightfield plus object triangles in a
// uniform grid (N3C2), or the legacy N3C1 triangle soup as objects. Queries
// gather the triangles whose padded X/Z bounds meet a box and callers run the
// exact triangle tests on that subset. Membership is decided per triangle
// from its own bounds, as in server/src/collision.rs, so both runtimes gather
// the same set and give the full scan's answers.
#include <array>
#include <cstdint>
#include <vector>
namespace n3e {
using V = std::array<float, 3>;
float collision_pad(float extent);
class Collision {
public:
  struct Terrain {
    uint32_t width = 0, depth = 0, diagonal = 0;
    float ox = 0, oz = 0, spacing = 1;
    std::vector<float> heights;
    V vertex(uint32_t i, uint32_t j) const;
    void cell(uint32_t i, uint32_t j, std::vector<V> &out) const;
  };
  Collision() = default;
  // N3C1 (or a test's own triangles); throws only on a partial triangle.
  explicit Collision(std::vector<V> soup);
  Collision(Terrain terrain, std::vector<V> objects);
  std::vector<V> near(float x0, float z0, float x1, float z1) const;
  std::vector<V> around(float x, float z, float reach) const {
    return near(x - reach, z - reach, x + reach, z + reach);
  }
  // Both ends of p..p+d, grown by r: camera sweeps and pick rays.
  std::vector<V> segment(const V &p, const V &d, float r) const;
  // Every triangle in near()'s order (terrain row major, then objects).
  std::vector<V> all() const;
  size_t triangles() const;
  bool empty() const { return triangles() == 0; }
  bool has_terrain() const { return terrain_.width != 0; }
  const Terrain &terrain() const { return terrain_; }
  size_t memory() const;
  // Highest surface of any triangle at X/Z, walls included.
  float ground_height(float x, float z) const;

private:
  struct Bounds { float x0, z0, x1, z1; };
  void build();
  void range(float lo, float hi, float origin, uint32_t samples, int64_t &a, int64_t &b) const;
  Terrain terrain_;
  std::vector<V> objects_;
  std::vector<Bounds> bounds_;
  float gx_ = 0, gz_ = 0, cell_ = 4;
  size_t nx_ = 0, nz_ = 0;
  std::vector<uint32_t> start_, ids_, large_;
};
} // namespace n3e
