#include "collision.h"
#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>
namespace n3e {
namespace {
// Same constants as server/src/collision.rs. The grid never refuses a
// package: at most SPREAD memberships per triangle, the rest always scanned.
constexpr float CELL = 4, MAX_CELLS = 1024;
constexpr size_t SPREAD = 64;
} // namespace
float collision_pad(float extent) { return .25f + extent * 1e-4f; }
V Collision::Terrain::vertex(uint32_t i, uint32_t j) const {
  return {float(double(ox) + double(i) * double(spacing)), heights[size_t(j) * width + i],
          float(double(oz) + double(j) * double(spacing))};
}
void Collision::Terrain::cell(uint32_t i, uint32_t j, std::vector<V> &out) const {
  V a = vertex(i, j), b = vertex(i, j + 1), c = vertex(i + 1, j), d = vertex(i + 1, j + 1);
  uint32_t phase = diagonal == 2 ? 1 : 0;
  if (diagonal != 0 && (i + j + phase) % 2 == 1)
    out.insert(out.end(), {a, b, d, a, d, c});
  else
    out.insert(out.end(), {a, b, c, c, b, d});
}
Collision::Collision(std::vector<V> soup) : objects_(std::move(soup)) {
  if (objects_.size() % 3)
    throw std::runtime_error("collision triangles");
  build();
}
Collision::Collision(Terrain terrain, std::vector<V> objects) : Collision(std::move(objects)) {
  if (terrain.width < 2 || terrain.depth < 2 || terrain.heights.size() != size_t(terrain.width) * terrain.depth ||
      !(terrain.spacing > 0))
    throw std::runtime_error("collision heightfield");
  terrain_ = std::move(terrain);
}
void Collision::build() {
  bounds_.clear();
  for (size_t i = 0; i < objects_.size(); i += 3) {
    const V &a = objects_[i], &b = objects_[i + 1], &c = objects_[i + 2];
    float x0 = std::min({a[0], b[0], c[0]}), x1 = std::max({a[0], b[0], c[0]});
    float z0 = std::min({a[2], b[2], c[2]}), z1 = std::max({a[2], b[2], c[2]});
    float m = collision_pad(std::max(x1 - x0, z1 - z0));
    bounds_.push_back({x0 - m, z0 - m, x1 + m, z1 + m});
  }
  if (bounds_.empty())
    return;
  float x0 = std::numeric_limits<float>::infinity(), z0 = x0, x1 = -x0, z1 = -x0;
  for (const auto &b : bounds_) {
    x0 = std::min(x0, b.x0); z0 = std::min(z0, b.z0);
    x1 = std::max(x1, b.x1); z1 = std::max(z1, b.z1);
  }
  gx_ = x0; gz_ = z0;
  cell_ = std::max(CELL, std::max(x1 - x0, z1 - z0) / MAX_CELLS);
  nx_ = size_t((x1 - x0) / cell_) + 1;
  nz_ = size_t((z1 - z0) / cell_) + 1;
  auto span = [&](float lo, float hi, float o, size_t n, size_t &a, size_t &b) {
    auto c = [&](float v) { return std::min(size_t(std::max(std::floor((v - o) / cell_), 0.f)), n - 1); };
    a = c(lo); b = c(hi);
  };
  std::vector<size_t> count(nx_ * nz_, 0);
  std::vector<std::array<size_t, 4>> spans(bounds_.size());
  std::vector<bool> listed(bounds_.size(), false);
  for (size_t i = 0; i < bounds_.size(); ++i) {
    auto &s = spans[i];
    span(bounds_[i].x0, bounds_[i].x1, gx_, nx_, s[0], s[1]);
    span(bounds_[i].z0, bounds_[i].z1, gz_, nz_, s[2], s[3]);
    if ((s[1] - s[0] + 1) * (s[3] - s[2] + 1) > SPREAD) {
      large_.push_back(uint32_t(i));
      listed[i] = true;
      continue;
    }
    for (size_t z = s[2]; z <= s[3]; ++z)
      for (size_t x = s[0]; x <= s[1]; ++x)
        ++count[z * nx_ + x];
  }
  size_t total = 0;
  for (auto c : count)
    total += c;
  start_.assign(nx_ * nz_ + 1, 0);
  for (size_t k = 0; k < count.size(); ++k)
    start_[k + 1] = start_[k] + uint32_t(count[k]);
  std::vector<uint32_t> fill(start_.begin(), start_.end() - 1);
  ids_.assign(total, 0);
  for (size_t i = 0; i < bounds_.size(); ++i) {
    if (listed[i])
      continue;
    const auto &s = spans[i];
    for (size_t z = s[2]; z <= s[3]; ++z)
      for (size_t x = s[0]; x <= s[1]; ++x)
        ids_[fill[z * nx_ + x]++] = uint32_t(i);
  }
}
void Collision::range(float lo, float hi, float origin, uint32_t samples, int64_t &a, int64_t &b) const {
  double s = terrain_.spacing;
  double ring = std::ceil(double(collision_pad(terrain_.spacing)) / s) + 1;
  double first = std::floor((double(lo) - origin) / s) - ring, last = std::floor((double(hi) - origin) / s) + ring;
  double end = double(samples) - 2;
  if (last < 0 || first > end) {
    a = 0; b = -1;
    return;
  }
  a = int64_t(std::max(first, 0.)); b = int64_t(std::min(last, end));
}
std::vector<V> Collision::near(float x0, float z0, float x1, float z1) const {
  std::vector<V> out;
  if (!std::isfinite(x0) || !std::isfinite(z0) || !std::isfinite(x1) || !std::isfinite(z1) || x0 > x1 || z0 > z1)
    return out;
  if (has_terrain()) {
    int64_t i0, i1, j0, j1;
    range(x0, x1, terrain_.ox, terrain_.width, i0, i1);
    range(z0, z1, terrain_.oz, terrain_.depth, j0, j1);
    for (int64_t j = j0; j <= j1 && i0 <= i1; ++j)
      for (int64_t i = i0; i <= i1; ++i)
        terrain_.cell(uint32_t(i), uint32_t(j), out);
  }
  if (bounds_.empty())
    return out;
  // Listed triangles first (ascending), then the cells' (ascending, once each).
  auto meets = [&](uint32_t i) {
    const auto &r = bounds_[i];
    return r.x0 <= x1 && r.x1 >= x0 && r.z0 <= z1 && r.z1 >= z0;
  };
  auto push = [&](uint32_t i) {
    out.insert(out.end(), objects_.begin() + size_t(i) * 3, objects_.begin() + size_t(i) * 3 + 3);
  };
  for (auto i : large_)
    if (meets(i))
      push(i);
  std::vector<uint32_t> ids;
  float gx1 = gx_ + float(nx_) * cell_, gz1 = gz_ + float(nz_) * cell_;
  if (x1 >= gx_ && x0 <= gx1 && z1 >= gz_ && z0 <= gz1) {
    auto c = [&](float v, float o, size_t n) { return std::min(size_t(std::max(std::floor((v - o) / cell_), 0.f)), n - 1); };
    for (size_t z = c(z0, gz_, nz_); z <= c(z1, gz_, nz_); ++z)
      for (size_t x = c(x0, gx_, nx_); x <= c(x1, gx_, nx_); ++x) {
        size_t k = z * nx_ + x;
        ids.insert(ids.end(), ids_.begin() + start_[k], ids_.begin() + start_[k + 1]);
      }
  }
  std::sort(ids.begin(), ids.end());
  ids.erase(std::unique(ids.begin(), ids.end()), ids.end());
  for (auto i : ids)
    if (meets(i))
      push(i);
  return out;
}
std::vector<V> Collision::segment(const V &p, const V &d, float r) const {
  return near(std::min(p[0], p[0] + d[0]) - r, std::min(p[2], p[2] + d[2]) - r,
              std::max(p[0], p[0] + d[0]) + r, std::max(p[2], p[2] + d[2]) + r);
}
std::vector<V> Collision::all() const {
  std::vector<V> out;
  out.reserve(triangles() * 3);
  if (has_terrain())
    for (uint32_t j = 0; j + 1 < terrain_.depth; ++j)
      for (uint32_t i = 0; i + 1 < terrain_.width; ++i)
        terrain_.cell(i, j, out);
  out.insert(out.end(), objects_.begin(), objects_.end());
  return out;
}
size_t Collision::triangles() const {
  return (has_terrain() ? size_t(terrain_.width - 1) * (terrain_.depth - 1) * 2 : 0) + objects_.size() / 3;
}
size_t Collision::memory() const {
  return terrain_.heights.size() * 4 + objects_.size() * 12 + bounds_.size() * 16 +
         (start_.size() + ids_.size() + large_.size()) * 4;
}
float Collision::ground_height(float x, float z) const {
  float best = -std::numeric_limits<float>::infinity();
  auto t = around(x, z, 0);
  for (size_t i = 0; i < t.size(); i += 3) {
    auto a = t[i], b = t[i + 1], c = t[i + 2];
    float d = (b[2] - c[2]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[2] - c[2]);
    if (std::abs(d) < 1e-8)
      continue;
    float u = ((b[2] - c[2]) * (x - c[0]) + (c[0] - b[0]) * (z - c[2])) / d,
          v = ((c[2] - a[2]) * (x - c[0]) + (a[0] - c[0]) * (z - c[2])) / d;
    if (u >= -1e-6 && v >= -1e-6 && u + v <= 1 + 1e-6)
      best = std::max(best, u * a[1] + v * b[1] + (1 - u - v) * c[1]);
  }
  return best;
}
} // namespace n3e
