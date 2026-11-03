#pragma once
// RQ-126 (N3FE version 20): create's slide, as 1298's in-select create slides
// its three panels in each time it opens (specs/KO-FINDINGS.md 9.15, binary):
// SetVisible (00606650) sets the slide's flag and its distance to 0, and each
// Tick (00606450) while the flag is set adds max(t 1300 (w - d) / w, 2) to the
// distance, t the frame's seconds and w Group_race's width, then puts
// Group_race at max(W - d, W - w - 50), clearing the flag there, Group_class at
// min(d - w_c, 50) and Group_name at max(H - trunc((h + 30) d / (w_c + 50)),
// H - 30 - h). The package says it as data (FrontSlide, content/front-end.md
// item 13): each node from its start toward its rest (where the layout's moves
// put it) by trunc(num d / den), the lead's arrival ending the slide. Kept
// free of GL so tests/front_end.cpp can run it; render/front_end.h moves the
// create layout's nodes with it.
#include "assets/assets.h"
#include "assets/front_place.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <vector>

namespace n3e::front {

// A distance past which a slide ends whatever its lead does (a bound; every
// node is then at rest). d grows by at least the floor a frame: the loader
// takes a floor of at least 1/16, the float step just below 10^6, so a float
// d always reaches this bound and every slide ends.
inline constexpr float kSlideBound = 1e6f;

struct SlideState {
  float d = 0;        // 1298's +0xb8, a float
  bool on = false;    // its flag +0xbc
  bool rest = true;   // every node where the moves put it (no slide yet, or a test hook's rest)
};

inline void slide_open(SlideState &s) { s = {0, true, false}; }
inline void slide_rest(SlideState &s) { s = {0, false, true}; }

// A node's coordinate on its axis at distance d: from `start` toward `rest`
// by trunc(num d / den) (C's cast, toward zero), never past `rest`.
inline double slide_at(const FrontSlideNode &n, double start, double rest, float d) {
  const double moved = std::trunc(double(n.num) * double(d) / double(n.den));
  return start <= rest ? std::min(start + moved, rest) : std::max(start - moved, rest);
}

// Each slid node's top-left coordinate on its axis this frame, on a placement
// `extent` (the window's size, or the canvas's when scaled) whose layout rects
// (the moves applied) are `rects`: its rest when the slide is at rest.
inline std::vector<double> slide_coordinates(const FrontSlide &slide, const std::vector<std::array<float, 4>> &rects,
                                             std::array<int, 2> extent, const SlideState &s) {
  std::vector<double> at;
  for (const auto &n : slide.nodes) {
    const double rest = rects.at(n.node)[n.axis];
    at.push_back(s.rest ? rest : slide_at(n, front_axis_at(n.start, extent[n.axis], rest), rest, s.d));
  }
  return at;
}

// One frame of `dt` seconds (1298's Tick): nothing unless the slide is on and
// time has passed; d grows by max(dt rate (w - d) / w, floor), w the lead's
// extent on its axis, stored as a float as 1298 stores it; the frame the lead
// is at its rest (on or past it before the clamp) the slide ends.
inline void slide_tick(const FrontSlide &slide, const std::vector<std::array<float, 4>> &rects,
                       std::array<int, 2> extent, SlideState &s, double dt) {
  if (!s.on || slide.nodes.empty() || !(dt > 0)) return;
  const auto &lead = slide.nodes.front();
  const auto &r = rects.at(lead.node);
  const double w = double(r[lead.axis + 2]) - double(r[lead.axis]);
  const double step = dt * double(slide.rate) * (w - double(s.d)) / w;
  s.d = float(double(s.d) + std::max(step, double(slide.floor)));
  const double rest = r[lead.axis];
  if (slide_at(lead, front_axis_at(lead.start, extent[lead.axis], rest), rest, s.d) == rest) s.on = false;
  if (s.d >= kSlideBound) slide_rest(s);
}

}  // namespace n3e::front
