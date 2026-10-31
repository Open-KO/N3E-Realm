#pragma once
#include "assets/assets.h"
#include "platform/gl.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdlib>
#include <vector>

// N3WO (PQ-387, D-204): the maps an N3WO overlay blends over the near terrain
// patches within `window` patches of the eye's patch. Like 1298's 3 x 3 window
// (0059b890 -> 0059ba90 / 0059c450 reload it when the eye's patch changes),
// only the window's maps are on the GPU: one array of layers(), slot
// ((dz + w) * (2w + 1) + dx + w) * per_patch^2 + local block, rewritten when the
// eye's patch moves. Each near patch's draw takes its blocks' layers (-1 none).
struct TerrainOverlay {
  n3e::WorldOverlay overlay;
  GLuint texture = 0;
  int cx = 0, cz = 0;
  bool placed = false;
  uint64_t uploads = 0;

  void create(n3e::WorldOverlay o) {
    overlay = std::move(o);
    glGenTextures(1, &texture);
    glActiveTexture(GL_TEXTURE9);
    glBindTexture(GL_TEXTURE_2D_ARRAY, texture);
    for (uint32_t k = 0; k < overlay.levels; ++k)
      glTexImage3D(GL_TEXTURE_2D_ARRAY, k, GL_RGBA8, overlay.side >> k, overlay.side >> k, overlay.layers(), 0, GL_RGBA,
                   GL_UNSIGNED_BYTE, nullptr);
    glTexParameteri(GL_TEXTURE_2D_ARRAY, GL_TEXTURE_MAX_LEVEL, overlay.levels - 1);
    // 1298: LINEAR min, mag and mip filters (005c4caa-005c4d0e) and MIRROR
    // addressing on stage 0 (0059d0ca) while the terrain draws.
    glTexParameteri(GL_TEXTURE_2D_ARRAY, GL_TEXTURE_MIN_FILTER, GL_LINEAR_MIPMAP_LINEAR);
    glTexParameteri(GL_TEXTURE_2D_ARRAY, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D_ARRAY, GL_TEXTURE_WRAP_S, GL_MIRRORED_REPEAT);
    glTexParameteri(GL_TEXTURE_2D_ARRAY, GL_TEXTURE_WRAP_T, GL_MIRRORED_REPEAT);
    glActiveTexture(GL_TEXTURE0);
  }

  // The eye's patch, as world_lod::terrain_level takes it (truncation).
  static std::array<int, 2> eye_patch(const n3e::TerrainDetail &t, const n3e::V &eye) {
    return {int((eye[0] - t.origin[0]) / t.patch_size), int((t.origin[2] - eye[2]) / t.patch_size)};
  }

  // Uploads the window's maps when the eye's patch changed.
  void follow(const n3e::TerrainDetail &t, const n3e::V &eye) {
    const auto [x, z] = eye_patch(t, eye);
    if (placed && x == cx && z == cz) return;
    cx = x; cz = z; placed = true;
    const int w = int(overlay.window), per = int(overlay.per_patch()), side = 2 * w + 1;
    glActiveTexture(GL_TEXTURE9);
    glBindTexture(GL_TEXTURE_2D_ARRAY, texture);
    glPixelStorei(GL_UNPACK_ALIGNMENT, 1);
    for (int dz = -w; dz <= w; ++dz)
      for (int dx = -w; dx <= w; ++dx)
        for (int bz = 0; bz < per; ++bz)
          for (int bx = 0; bx < per; ++bx) {
            const auto *at = find((cx + dx) * per + bx, (cz + dz) * per + bz);
            if (!at) continue;
            const int layer = ((dz + w) * side + dx + w) * per * per + bz * per + bx;
            size_t offset = 0;
            for (uint32_t k = 0; k < overlay.levels; ++k) {
              const int s = int(overlay.side >> k);
              glTexSubImage3D(GL_TEXTURE_2D_ARRAY, k, 0, 0, layer, s, s, 1, GL_RGBA, GL_UNSIGNED_BYTE, at + offset);
              offset += size_t(s) * s * 4;
            }
            ++uploads;
          }
    glActiveTexture(GL_TEXTURE0);
  }

  // A patch's block layers (per_patch^2, x fastest; -1 where its block has no
  // map), or false when the patch is outside the window or has no map.
  bool layers(uint32_t px, uint32_t pz, std::array<int, 16> &out) const {
    const int w = int(overlay.window), per = int(overlay.per_patch()), side = 2 * w + 1;
    const int dx = int(px) - cx, dz = int(pz) - cz;
    if (!placed || std::abs(dx) > w || std::abs(dz) > w) return false;
    bool any = false;
    out.fill(-1);
    for (int bz = 0; bz < per; ++bz)
      for (int bx = 0; bx < per; ++bx)
        if (find(int(px) * per + bx, int(pz) * per + bz)) {
          out[size_t(bz * per + bx)] = ((dz + w) * side + dx + w) * per * per + bz * per + bx;
          any = true;
        }
    return any;
  }

  // Whether some block of patch (px, pz) has a map, inside the window or not:
  // the test client counts near patches the window keeps their maps off.
  bool any_map(uint32_t px, uint32_t pz) const {
    const int per = int(overlay.per_patch());
    for (int bz = 0; bz < per; ++bz)
      for (int bx = 0; bx < per; ++bx)
        if (find(int(px) * per + bx, int(pz) * per + bz)) return true;
    return false;
  }

  const unsigned char *find(int bx, int bz) const {
    const int width = int(overlay.width);
    if (bx < 0 || bz < 0 || bx >= width || bz >= width) return nullptr;
    auto it = overlay.maps.find(uint32_t(bz * width + bx));
    return it == overlay.maps.end() ? nullptr : overlay.bytes.data() + it->second;
  }

  void bind() const {
    glActiveTexture(GL_TEXTURE9);
    glBindTexture(GL_TEXTURE_2D_ARRAY, texture);
    glActiveTexture(GL_TEXTURE0);
  }
};
