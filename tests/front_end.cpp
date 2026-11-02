// Spec 11 acceptance 2: the client's front-end.bin loader on the synthetic
// blobs tests/front_end.py writes. Arguments are pairs: `ok DIR` must load,
// `bad DIR` must be refused with a message (never a crash). A loaded
// package's music tracks must stream. RQ-067: the select camera's turn
// (client/render/select_turn.h) on a camera with the Karus eye's offset from
// `at`, looking along +z from -z, where an absolute heading wraps at +-pi.
#include "assets/assets.h"
#include "render/select_turn.h"
#include <algorithm>
#include <cmath>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
using n3e::V;
// KO's own check (1097: 0043dc50, 0043dfb0): the eye turned a further 0.01 rad
// has a cosine with the camera's own eye, both from `at`, below `end`.
bool ko_check_ends(const V &home, const V &at, float angle, float dir, float end) {
  const V e = n3e::front::select_eye(home, at, angle + dir * .01f);
  float dot = 0, a = 0, b = 0;
  for (int i = 0; i < 3; ++i) {
    const float x = home[i] - at[i], y = e[i] - at[i];
    dot += x * y, a += x * x, b += y * y;
  }
  return dot / std::sqrt(a * b) < end;
}

// One turn from `from` to `goal` at a fixed frame time: each tick's angle
// before it (the angle its check sees), the last tick's being the one that
// ended the turn, and the angle after the turn. Fails on a frame outside the
// two slots' angles (less one step past either) or on more frames than the
// shortest way takes.
std::string turn(std::vector<float> &checked, float &after, float from, float goal, float dt) {
  float angle = from;
  const float step = n3e::front::kSelectTurnRate * dt;
  const float lo = std::min(from, goal) - step, hi = std::max(from, goal) + step;
  const int most = int(std::abs(goal - from) / step) + 3;
  for (int i = 0; i < most; ++i) {
    checked.push_back(angle);
    const bool ended = n3e::front::select_turn_tick(angle, from, goal, dt);
    after = angle;
    if (angle < lo || angle > hi) return "left the slots' angles: " + std::to_string(angle);
    if (ended) return "";
  }
  return "did not end";
}

std::string turn_check() {
  using namespace n3e::front;
  const V home{0, .2f, -7.4f}, at{0, 0, 0};
  if (select_turn(home, at, home) != 0) return "the camera's own eye is not turn 0";
  // The package's eyes: the side slots' where KO's check ends the turn
  // (tools/assetc/ko_front_end.py turn_end_eye, mirrored into engine space).
  const float left_end = .7130103f, right_end = -.6822184f;
  const V left = select_eye(home, at, left_end), right = select_eye(home, at, right_end);
  if (std::abs(select_turn(home, at, left) - left_end) > 1e-5f ||
      std::abs(select_turn(home, at, right) - right_end) > 1e-5f)
    return "select_turn does not invert select_eye";
  // Left is +x: the eye moves to the side of the slot it turns to.
  if (left[0] <= 0 || right[0] >= 0) return "a turn moves the eye to the wrong side";
  for (const float dt : {1 / 30.f, 1 / 60.f, 1 / 144.f, .25f}) {
    const float step = kSelectTurnRate * dt;
    for (const auto &[goal, end] : {std::pair{left_end, .75f}, std::pair{right_end, .77f}}) {
      std::vector<float> out, back;
      float last = 0, home_again = 1;
      if (auto e = turn(out, last, 0, goal, dt); !e.empty()) return "out: " + e;
      const float dir = goal > 0 ? 1.f : -1.f;
      // It ends on the first tick KO's own check ends it, not moving, one
      // step past the cooked angle at most.
      for (size_t i = 0; i + 1 < out.size(); ++i)
        if (ko_check_ends(home, at, out[i], dir, end)) return "out: it turned on past KO's end";
      if (!ko_check_ends(home, at, out.back(), dir, end)) return "out: it ended before KO's end";
      if (last != out.back()) return "out: the ending tick moved the eye";
      if ((last - goal) * dir <= 0 || (last - goal) * dir > step + 1e-5f) return "out: the end overshoots";
      // Back: from where it ended to the camera's own eye (KO: until the
      // eye's x is past 0), put back on it.
      if (auto e = turn(back, home_again, last, 0, dt); !e.empty()) return "back: " + e;
      for (size_t i = 0; i + 1 < back.size(); ++i)
        if (back[i] * dir <= 0) return "back: it turned on past the camera's own eye";
      if (back.back() * dir > 0) return "back: it ended before the camera's own eye";
      if (home_again != 0) return "back: not on the camera's own eye";
    }
  }
  return "";
}
}  // namespace

int main(int argc, char **argv) {
  if (const auto e = turn_check(); !e.empty()) {
    std::cerr << "FAIL select turn: " << e << "\n";
    return 1;
  }
  std::cout << "PASS select turn: one slot's turn each way, ended where 1097's check ends it\n";
  int loaded = 0, refused = 0;
  for (int i = 1; i + 1 < argc; i += 2) {
    const std::string want = argv[i];
    n3e::Release release;
    release.front_end = true;
    release.root = argv[i + 1];
    std::string error;
    try {
      const auto fe = n3e::load_front_end(release);
      if (fe.screens.size() != 5 || fe.slots.size() != fe.character_slots) error = "loaded inconsistently";
      // RQ-018: every loaded track streams (tests/audio.cpp checks the samples).
      for (const auto &track : fe.music) {
        n3e::MusicStream stream(track);
        std::vector<float> out(4800 * 2);
        if (stream.mix(out.data(), 4800, 1) == 0) error = "a loaded track does not stream";
      }
    } catch (const std::exception &e) {
      error = e.what();
    }
    if (want == "ok" && error.empty()) ++loaded;
    else if (want == "bad" && !error.empty()) ++refused;
    else {
      std::cerr << "FAIL front-end loader " << argv[i + 1] << ": " << (error.empty() ? "accepted" : error) << "\n";
      return 1;
    }
    if (want == "bad") std::cout << "refused " << release.root.filename().string() << ": " << error << "\n";
  }
  std::cout << "PASS front-end loader: " << loaded << " loaded, " << refused << " refused\n";
  return loaded && refused ? 0 : 1;
}
