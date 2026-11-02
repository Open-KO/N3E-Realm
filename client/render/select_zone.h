#pragma once
// The zone the select hall draws (front-end.bin version 8, RQ-095,
// content/front-end.md): 1298's select draws the karus_intro zone's terrain
// and shapes under its lights and the camera's fog, and its shapes' alpha
// parts after the UI (binary, specs/KO-FINDINGS.md 8.4). Kept free of GL so
// tests/front_end.cpp can run it; render/front_end.h draws with it.
#include "assets/assets.h"
#include <algorithm>
#include <cmath>
#include <numeric>
#include <vector>

namespace n3e::front {

// D3DFOG_LINEAR's factor, the share of the lit colour kept: 1 up to `start`
// metres from the eye, 0 from `end` on, linear between (D3D's
// (end - d) / (end - start)). 1298's select sets range fog (004395c0:
// D3DRS_RANGEFOGENABLE), so `d` is the distance from the eye; the shader in
// render/front_end.h takes it per pixel, D3D per vertex.
inline float fog_factor(float distance, float start, float end) {
  if (!(end > start)) return 1.f;
  return std::clamp((end - distance) / (end - start), 0.f, 1.f);
}

// The order the alpha flush (0043dd80) draws the zone's BLEND meshes in: far
// to near by the eye's distance to each one's sort point, a tie in file order.
inline std::vector<size_t> far_to_near(const std::vector<FrontZoneMesh> &zone, const V &eye) {
  std::vector<size_t> order;
  std::vector<float> distance(zone.size(), 0.f);
  for (size_t i = 0; i < zone.size(); ++i) {
    if (!(zone[i].mesh.flags & FrontMesh::BLEND)) continue;
    const auto &p = zone[i].sort;
    distance[i] = std::hypot(p[0] - eye[0], p[1] - eye[1], p[2] - eye[2]);
    order.push_back(i);
  }
  std::stable_sort(order.begin(), order.end(), [&](size_t a, size_t b) { return distance[a] > distance[b]; });
  return order;
}

}  // namespace n3e::front
