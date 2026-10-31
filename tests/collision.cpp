// PQ-215 client collision check.
//   n3e-collision-check probe FILE QUERIES   decode identity, memory and, per
//     "x z dx dz mode multiplier" line, walkable ground and one advance, in the
//     same format as `n3e-server --collision-probe`.
//   n3e-collision-check compare FILE SAMPLES gathered answers (ground height,
//     walk, advance, camera sweep, pick ray) against the full scan.
#include "assets/assets.h"
#include "network/world.h"
#include "render/orbit.h"
#include <chrono>
#include <cstdio>
#include <fstream>
#include <iostream>
#include <sstream>
#include <cstring>
#include <set>
using n3e::V;
static V sub3(V a, V b) { return {a[0] - b[0], a[1] - b[1], a[2] - b[2]}; }
static V add3(V a, V b) { return {a[0] + b[0], a[1] + b[1], a[2] + b[2]}; }
static V mul3(V a, double s) { return {float(a[0] * s), float(a[1] * s), float(a[2] * s)}; }
static double dot3(V a, V b) { return double(a[0]) * b[0] + double(a[1]) * b[1] + double(a[2]) * b[2]; }
static V cross3(V a, V b) { return {a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]}; }
static double length3(V a) { return std::sqrt(dot3(a, a)); }
// Closest point on triangle abc to p (Ericson, Real-Time Collision Detection 5.1.5).
static V closest_on_triangle(V p, V a, V b, V c) {
  V ab = sub3(b, a), ac = sub3(c, a), ap = sub3(p, a);
  double d1 = dot3(ab, ap), d2 = dot3(ac, ap);
  if (d1 <= 0 && d2 <= 0) return a;
  V bp = sub3(p, b);
  double d3 = dot3(ab, bp), d4 = dot3(ac, bp);
  if (d3 >= 0 && d4 <= d3) return b;
  double vc = d1 * d4 - d3 * d2;
  if (vc <= 0 && d1 >= 0 && d3 <= 0) return add3(a, mul3(ab, d1 / (d1 - d3)));
  V cp = sub3(p, c);
  double d5 = dot3(ab, cp), d6 = dot3(ac, cp);
  if (d6 >= 0 && d5 <= d6) return c;
  double vb = d5 * d2 - d1 * d6;
  if (vb <= 0 && d2 >= 0 && d6 <= 0) return add3(a, mul3(ac, d2 / (d2 - d6)));
  double va = d3 * d6 - d5 * d4;
  if (va <= 0 && d4 - d3 >= 0 && d5 - d6 >= 0) return add3(b, mul3(sub3(c, b), (d4 - d3) / ((d4 - d3) + (d5 - d6))));
  double denom = 1 / (va + vb + vc);
  return add3(a, add3(mul3(ab, vb * denom), mul3(ac, vc * denom)));
}
// Distance between segments p1q1 and p2q2 (Ericson 5.1.9).
static double segment_segment(V p1, V q1, V p2, V q2) {
  V d1 = sub3(q1, p1), d2 = sub3(q2, p2), r = sub3(p1, p2);
  double a = dot3(d1, d1), e = dot3(d2, d2), f = dot3(d2, r), s = 0, t = 0;
  if (a <= 1e-12 && e <= 1e-12) return length3(r);
  if (a <= 1e-12) t = std::clamp(f / e, 0., 1.);
  else {
    double c = dot3(d1, r);
    if (e <= 1e-12) s = std::clamp(-c / a, 0., 1.);
    else {
      double b = dot3(d1, d2), denom = a * e - b * b;
      s = denom > 1e-12 ? std::clamp((b * f - c * e) / denom, 0., 1.) : 0;
      t = (b * s + f) / e;
      if (t < 0) { t = 0; s = std::clamp(-c / a, 0., 1.); }
      else if (t > 1) { t = 1; s = std::clamp((b - c) / a, 0., 1.); }
    }
  }
  return length3(sub3(add3(p1, mul3(d1, s)), add3(p2, mul3(d2, t))));
}
// Exact distance between segment pq and triangle abc: zero if the segment
// crosses it, else the least of its ends to the triangle and its edges to the segment.
static double distance(V p, V q, V a, V b, V c) {
  V n = cross3(sub3(b, a), sub3(c, a));
  double dp = dot3(n, sub3(p, a)), dq = dot3(n, sub3(q, a));
  if (dp * dq <= 0 && dp != dq) {
    V x = add3(p, mul3(sub3(q, p), dp / (dp - dq)));
    if (length3(sub3(closest_on_triangle(x, a, b, c), x)) < 1e-6) return 0;
  }
  double best = std::min(length3(sub3(closest_on_triangle(p, a, b, c), p)), length3(sub3(closest_on_triangle(q, a, b, c), q)));
  for (auto [u, v] : {std::pair{a, b}, std::pair{b, c}, std::pair{c, a}})
    best = std::min(best, segment_segment(u, v, p, q));
  return best;
}
static std::array<float, 9> key(const std::vector<V> &t, size_t i) {
  return {t[i][0], t[i][1], t[i][2], t[i + 1][0], t[i + 1][1], t[i + 1][2], t[i + 2][0], t[i + 2][1], t[i + 2][2]};
}
int main(int argc, char **argv) {
  try {
    if (argc != 4)
      throw std::runtime_error("usage: probe|compare FILE ARG");
    auto start = std::chrono::steady_clock::now();
    auto c = n3e::load_collision(argv[2]);
    double load = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - start).count();
    auto all = c.all();
    uint64_t hash = 0xcbf29ce484222325ull;
    float lo[2] = {INFINITY, INFINITY}, hi[2] = {-INFINITY, -INFINITY};
    for (const auto &p : all) {
      for (float v : p) {
        uint32_t bits;
        std::memcpy(&bits, &v, 4);
        for (int k = 0; k < 4; ++k)
          hash = (hash ^ ((bits >> (8 * k)) & 0xff)) * 0x100000001b3ull;
      }
      lo[0] = std::min(lo[0], p[0]); lo[1] = std::min(lo[1], p[2]);
      hi[0] = std::max(hi[0], p[0]); hi[1] = std::max(hi[1], p[2]);
    }
    char header[160];
    std::snprintf(header, sizeof header, "collision triangles %zu terrain %d hash %016llx memory %zu load_ms %.1f",
                  c.triangles(), c.has_terrain() ? 1 : 0, (unsigned long long)hash, c.memory(), load);
    std::cout << header << "\n";
    n3e::MovementConfig cfg{3, 6, 1.5f, .35f, 1.8f, .4f};
    if (std::string(argv[1]) == "probe") {
      std::ifstream in(argv[3]);
      std::string line;
      while (std::getline(in, line)) {
        std::istringstream s(line);
        float x, z, dx, dz, mode, m;
        if (!(s >> x >> z >> dx >> dz >> mode >> m))
          throw std::runtime_error("collision query line");
        // Walkable support, as the server's movement::ground.
        float g = -INFINITY;
        {
          auto t = c.around(x, z, 0);
          float y = -INFINITY;
          for (size_t i = 0; i < t.size(); i += 3) {
            auto a = t[i], b = t[i + 1], cc = t[i + 2];
            n3e::V u{b[0] - a[0], b[1] - a[1], b[2] - a[2]}, v{cc[0] - a[0], cc[1] - a[1], cc[2] - a[2]};
            n3e::V n{u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]};
            if (std::abs(n[1]) < .707107f * std::sqrt(n[0] * n[0] + n[1] * n[1] + n[2] * n[2]))
              continue;
            float d = (b[2] - cc[2]) * (a[0] - cc[0]) + (cc[0] - b[0]) * (a[2] - cc[2]);
            if (std::abs(d) < 1e-8)
              continue;
            float uu = ((b[2] - cc[2]) * (x - cc[0]) + (cc[0] - b[0]) * (z - cc[2])) / d;
            float vv = ((cc[2] - a[2]) * (x - cc[0]) + (a[0] - cc[0]) * (z - cc[2])) / d;
            if (uu >= -1e-6 && vv >= -1e-6 && uu + vv <= 1 + 1e-6)
              y = std::max(y, uu * a[1] + vv * b[1] + (1 - uu - vv) * cc[1]);
          }
          g = y;
        }
        if (std::isfinite(g)) {
          auto a = n3e::advance(c, {x, g, z}, dx, dz, uint32_t(mode), cfg, m);
          std::printf("%.9f %.9f %.9f %.9f\n", g, a[0], a[1], a[2]);
        } else
          std::printf("none\n");
      }
      return 0;
    }
    if (std::string(argv[1]) != "compare")
      throw std::runtime_error("mode");
    unsigned samples = unsigned(std::stoul(argv[3]));
    uint64_t seed = 0x2545f4914f6cdd1dull;
    auto f = [&] {
      seed ^= seed << 13; seed ^= seed >> 7; seed ^= seed << 17;
      return float(seed >> 40) / float(1ull << 24);
    };
    n3e::Scene full;
    full.collision = n3e::Collision(all);
    unsigned mismatches = 0, supported = 0, dropped = 0;
    for (unsigned k = 0; k < samples; ++k) {
      float x = lo[0] + (hi[0] - lo[0]) * f(), z = lo[1] + (hi[1] - lo[1]) * f();
      auto ground = [&](const std::vector<n3e::V> &t) {
        float best = -INFINITY;
        for (size_t i = 0; i < t.size(); i += 3) {
          auto a = t[i], b = t[i + 1], cc = t[i + 2];
          float d = (b[2] - cc[2]) * (a[0] - cc[0]) + (cc[0] - b[0]) * (a[2] - cc[2]);
          if (std::abs(d) < 1e-8)
            continue;
          float u = ((b[2] - cc[2]) * (x - cc[0]) + (cc[0] - b[0]) * (z - cc[2])) / d,
                v = ((cc[2] - a[2]) * (x - cc[0]) + (a[0] - cc[0]) * (z - cc[2])) / d;
          if (u >= -1e-6 && v >= -1e-6 && u + v <= 1 + 1e-6)
            best = std::max(best, u * a[1] + v * b[1] + (1 - u - v) * cc[1]);
        }
        return best;
      };
      float g = c.ground_height(x, z);
      bool same = g == ground(all) || (std::isnan(g) && std::isnan(ground(all)));
      float dx = f() * 2 - 1, dz = f() * 2 - 1, m = 1 + 9 * f();
      uint32_t mode = uint32_t(f() * 3);
      if (std::isfinite(g)) {
        ++supported;
        n3e::V p{x, g, z};
        same &= n3e::walk(c, p, dx, dz) == n3e::walk(all, p, dx, dz);
        same &= n3e::advance(c, p, dx, dz, mode, cfg, m) == n3e::advance(all, p, dx, dz, mode, cfg, m);
      }
      // Camera sweep and pick ray from above the point, as orbit.h does.
      n3e::V focus{x, (std::isfinite(g) ? g : 0) + 1.2f, z};
      n3e::V delta{(f() * 2 - 1) * 16, f() * 10, (f() * 2 - 1) * 16};
      float radius = .05f + .3f * f();
      auto sweep = [&](const std::vector<n3e::V> &t) {
        float fraction = 1;
        for (size_t i = 0; i < t.size(); i += 3)
          fraction = std::min(fraction, camera_geometry::hit(focus, delta, t[i], t[i + 1], t[i + 2], radius));
        return fraction;
      };
      // The gather is a subset, so it can only lose hits. Each lost hit must
      // be the slab test's corner overshoot (hit() pads each edge slab, which
      // reaches past the radius at an acute corner): a triangle left out whose
      // exact distance from the boom is more than the radius. Measured here;
      // one within the radius is a gather bug and fails the check.
      const auto gathered = c.segment(focus, delta, radius + 1.f);
      float swept = sweep(gathered), reference = sweep(all);
      if (swept < reference)
        same = false;
      if (swept > reference) {
        ++dropped;
        std::set<std::array<float, 9>> kept;
        for (size_t i = 0; i < gathered.size(); i += 3)
          kept.insert(key(gathered, i));
        for (size_t i = 0; i < all.size(); i += 3)
          if (camera_geometry::hit(focus, delta, all[i], all[i + 1], all[i + 2], radius) < swept &&
              !kept.count(key(all, i)) &&
              distance(focus, {focus[0] + delta[0], focus[1] + delta[1], focus[2] + delta[2]}, all[i], all[i + 1],
                       all[i + 2]) <= radius) {
            std::cerr << "camera gather left out a triangle within the radius\n";
            same = false;
          }
      }
      n3e::V ray{delta[0] * 6, -40 - f() * 60, delta[2] * 6};
      auto pick = [&](const std::vector<n3e::V> &t) {
        float nearest = 1;
        for (size_t i = 0; i < t.size(); i += 3) {
          float h = camera_geometry::hit(focus, ray, t[i], t[i + 1], t[i + 2], 0);
          if (h >= 0 && h < nearest)
            nearest = h;
        }
        return nearest;
      };
      float picked = pick(c.segment(focus, ray, 0)), nearest = pick(all);
      if (picked != nearest)
        std::cerr << "pick ray " << picked << " vs " << nearest << "\n";
      same &= picked == nearest;
      if (!same) {
        ++mismatches;
        std::cerr << "mismatch at " << x << " " << z << "\n";
      }
    }
    std::cout << "compare samples " << samples << " supported " << supported << " mismatches " << mismatches
              << " camera_corner_overshoot_dropped " << dropped << "\n";
    return mismatches ? 1 : 0;
  } catch (const std::exception &e) {
    std::cerr << e.what() << "\n";
    return 1;
  }
}
