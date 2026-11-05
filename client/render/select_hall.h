#pragma once
// The select hall's characters, spot and info text, tick by tick, as the KO
// client the package names plays them (front-end.bin's front-clip mode,
// content/front-end.md "Moradon"): 1097's hover (binary, specs/KO-FINDINGS.md
// 8.1) or 1298's loop (binary, 8 and 8.3). Kept free of GL so
// tests/front_end.cpp can run it; render/front_end.h poses and draws what it
// holds.
#include "assets/assets.h"
#include <algorithm>
#include <array>
#include <cmath>

namespace n3e::front {

// The select model's clips by role (load_front_end): the front clip (1097's
// pre_select, 1298's clip 1), the start clip (selected; 1298's clip 2) and the
// rest clip (dummy; 1298's clip 0).
inline constexpr size_t kFrontClip = 0, kStartClip = 1, kRestClip = 2;

// One slot's clip player, as CN3Chr's (1097 binary: the setter 00447e30, the
// frame tick 00445bb0; 1298: 0041be40, 00418700). Selecting the clip already
// set changes nothing; a negative blend is the clip's own blend time
// (FLT_MIN); a blend starts from the frame the previous clip had reached and
// keeps the new clip on its first frame until it ends; a clip played once
// holds its last frame, a looping one starts again at its first. A blend set
// during another starts from the frame that one's clip was held on (its
// first): KO keeps only the frame, not the blended pose (00447e30 stores
// +0x1c8 as the previous frame, +0x1d4, and the joints blend those two
// frames, 00445e90), so its pose jumps there.
struct HallPlayer {
  size_t slot = 0;                              // the slot it plays in (its clips' lengths and blends)
  size_t clip = kFrontClip, from = kFrontClip;  // the clip, the clip blended from
  float elapsed = 0, blend = 0, from_time = 0;  // ticked time since set; blend time; from's time
  bool loop = false;                            // the clip loops (1298: once flag 0)
};

struct SelectHall {
  using Roles = std::array<float, 3>;
  FrontClipMode mode = FrontClipMode::hover;
  // Per slot, per role: the clip's length and blend (seconds). RQ-005: each
  // slot's character draws its own model (its race and class, AddChr), whose
  // clips need not be the others'.
  std::array<Roles, 3> length{Roles{1, 1, 1}, Roles{1, 1, 1}, Roles{1, 1, 1}}, blends{};
  std::array<HallPlayer, 3> players{HallPlayer{0}, HallPlayer{1}, HallPlayer{2}};
  float theta = 0;      // the front spot's theta (1097 +0x2d0, 1298 +0x398)
  bool spot_on = false;
  int info_slot = -1;   // the slot whose info text shows, -1 none

  // CGameProcCharacterSelect::Init. AddChr ends by setting the front clip
  // with no blend on every character: 1097 pre_select once (0043cee1-
  // 0043cf0b), 1298 its clip 1 looping (005fb4f0's last loop,
  // 0041be40(1, 0, 0, 0, 1)). The spot is off and the info text hidden.
  void reset() {
    players = {};
    for (size_t i = 0; i < players.size(); ++i) {
      players[i].slot = i;
      players[i].loop = mode == FrontClipMode::loop;
    }
    theta = 0;
    spot_on = false;
    info_slot = -1;
  }
  void set(HallPlayer &p, size_t clip, float blend, bool loop = false) {
    if (clip == p.clip) return;
    p.from_time = played(p);
    p.from = p.clip;
    p.clip = clip;
    p.elapsed = 0;
    p.loop = loop;
    p.blend = blend < 0 ? blends[p.slot][clip] : blend;
  }
  float played(const HallPlayer &p) const {
    const float t = p.elapsed - p.blend, end = length[p.slot][p.clip];
    if (p.loop && t > 0) return std::fmod(t, end);
    return std::clamp(t, 0.f, end);
  }
  // IsAnimEnd: a clip played once has passed its end, after its blend.
  bool ended(const HallPlayer &p) const { return !p.loop && p.elapsed - p.blend >= length[p.slot][p.clip]; }
  // The clip the character in front returns to at rest: the hover mode's by
  // the pointer, the loop mode's front clip looping.
  void front_at_rest(HallPlayer &p, bool over) {
    if (mode == FrontClipMode::loop) set(p, kFrontClip, -1, true);
    else set(p, over ? kFrontClip : kRestClip, -1);
  }
  // One tick with the camera at rest on `focus` (1097 state 2, 1298 state
  // 5), `shown` characters in the hall, the pointer `over` the centre rect
  // or not, the front spot at most `widest`, growing by `rate` a second.
  // Hover (1097: DoProcPreselect 0043f280): the character in front plays the
  // front clip once while the pointer is over it and the rest clip (dummy)
  // otherwise, and is the only one ticked; the spot widens while the pointer
  // is there and narrows when it leaves, off at 0; the info text shows only
  // while it is there. Loop (1298: 005fef90): the character in front loops
  // the front clip and the others play the rest clip once, every character
  // ticked; the spot widens to its widest and stays; the info text shows,
  // whatever the pointer does.
  void rest(int focus, int shown, bool over, float widest, float rate, float dt) {
    if (mode == FrontClipMode::loop) {
      for (int i = 0; i < shown; ++i) {
        auto &p = players.at(size_t(i));
        if (i == focus) front_at_rest(p, over);
        else set(p, kRestClip, -1);
        p.elapsed += dt;
      }
      theta = std::min(theta + rate * dt, widest);
      spot_on = theta > 0;
      info_slot = focus;
      return;
    }
    if (focus < shown) {
      front_at_rest(players.at(size_t(focus)), over);
      players.at(size_t(focus)).elapsed += dt;
    }
    theta = std::clamp(theta + (over ? 1 : -1) * rate * dt, 0.f, widest);
    spot_on = theta > 0;
    info_slot = over ? focus : -1;
  }
  // One tick while the camera turns (1097 state 1, 1298 states 1, 2 and 6):
  // every light is off (1097 0043b550, 1298 005faf10 turn all eight off each
  // tick) and the spot keeps its theta. Hover: nobody is ticked. Loop
  // (005fe5b0): every character plays the rest clip once and is ticked, and
  // the info text is hidden (1298 hides the whole select UI while it turns,
  // 005fe3c0/005fe450, as render/front_end.h does in the path turn mode).
  void turning(int shown, float dt) {
    spot_on = false;
    if (mode != FrontClipMode::loop) return;
    for (int i = 0; i < shown; ++i) {
      set(players.at(size_t(i)), kRestClip, -1);
      players.at(size_t(i)).elapsed += dt;
    }
    info_slot = -1;
  }
  // The start (1097: 0043ea30; 1298: 005fe7c0): the start clip once with the
  // package's start blend, the spot at its widest; then only that character
  // is ticked (0043ed20, 005fea70).
  void start(int slot, float widest) {
    set(players.at(size_t(slot)), kStartClip, -1);
    theta = widest;
    spot_on = true;
  }
  void starting(int slot, float dt) { players.at(size_t(slot)).elapsed += dt; }
};

}  // namespace n3e::front
