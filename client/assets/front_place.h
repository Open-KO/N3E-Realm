#pragma once
// RQ-106 (Q82): where a front-end layout's nodes are on a window of a given
// size (content/front-end.md item 12). KO draws its UI on the screen's own
// pixels and places each layout's root, and some of its nodes, by the
// viewport's size every time the layout loads (specs/KO-FINDINGS.md 9.3); the
// package carries those placements as moves, and the canvas rects are the
// moves applied at the canvas's size. GL-free, for the loader's check and
// tests/front_end.cpp.
#include "assets/assets.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <vector>

namespace n3e {
// A top-left coordinate on an axis `extent` pixels long, or `keep` (KEEP):
// trunc(a S + c), or with HALF trunc(floor(S / 2) + a S + c); trunc is C's
// cast, toward zero (tools/assetc/ko_front_end.py axis_at).
inline double front_axis_at(const FrontAxis &rule, int extent, double keep) {
  if (rule.kind == FrontAxis::KEEP) return keep;
  const double half = rule.kind == FrontAxis::HALF ? double(extent / 2) : 0.0;
  return std::trunc(half + double(rule.a) * extent + double(rule.c));
}

// The nodes' rects on a window `width` x `height`: from the canvas rects, each
// move in order puts its node's top-left where its rules say and moves the
// node's subtree with it (MoveOffset). Nodes are in draw order, a parent
// before its children.
inline std::vector<std::array<float, 4>> front_place(const std::vector<FrontNode> &nodes,
                                                     const std::vector<FrontMove> &moves, int width, int height) {
  std::vector<std::array<float, 4>> rects(nodes.size());
  for (size_t i = 0; i < nodes.size(); ++i) rects[i] = nodes[i].rect;
  std::vector<char> inside(nodes.size());
  for (const auto &m : moves) {
    if (m.node >= nodes.size()) continue;
    const auto &r = rects[m.node];
    const double dx = front_axis_at(m.x, width, r[0]) - r[0], dy = front_axis_at(m.y, height, r[1]) - r[1];
    if (dx == 0 && dy == 0) continue;
    std::fill(inside.begin(), inside.end(), 0);
    inside[m.node] = 1;
    for (size_t j = m.node; j < nodes.size(); ++j) {
      if (j > m.node) inside[j] = inside[nodes[j].parent];
      if (!inside[j]) continue;
      rects[j][0] += float(dx), rects[j][2] += float(dx);
      rects[j][1] += float(dy), rects[j][3] += float(dy);
    }
  }
  return rects;
}

// A layout's nodes: the five screens (FrontScreen), then the logo's (none
// without one).
inline const std::vector<FrontNode> &front_layout(const FrontEnd &fe, size_t layout) {
  static const std::vector<FrontNode> none;
  if (layout == FrontEnd::kLogoLayout) return fe.logo ? fe.logo->nodes : none;
  return fe.screens.at(layout);
}
// Whether the client scales the canvas to fit a window of this size: the
// package's option, or a window smaller than the canvas (KO's placements
// would cut the layouts off there).
inline bool front_scaled(const FrontEnd &fe, int width, int height) {
  return fe.scale_to_window || width < int(fe.canvas_width) || height < int(fe.canvas_height);
}
// A layout's rects on the window: KO's placements on its own pixels, or (scaled)
// the canvas rects, which front_view takes to the window.
inline std::vector<std::array<float, 4>> front_layout_rects(const FrontEnd &fe, size_t layout, int width,
                                                            int height) {
  static const std::vector<FrontMove> none;
  return front_place(front_layout(fe, layout), front_scaled(fe, width, height) ? none : fe.moves.at(layout), width,
                     height);
}
// The scale and the x and y offsets that take front_layout_rects to window
// pixels: the canvas fitted and centred when scaled, none otherwise.
inline std::array<float, 3> front_view(const FrontEnd &fe, int width, int height) {
  if (!front_scaled(fe, width, height)) return {1.f, 0.f, 0.f};
  const float s = std::min(width / float(fe.canvas_width), height / float(fe.canvas_height));
  return {s, (width - fe.canvas_width * s) / 2, (height - fe.canvas_height * s) / 2};
}
} // namespace n3e
