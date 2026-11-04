// Spec 11 acceptance 2: the client's front-end.bin loader on the synthetic
// blobs tests/front_end.py writes. Arguments are pairs: `ok DIR` must load,
// `bad DIR` must be refused with a message (never a crash). A loaded
// package's music tracks must stream. RQ-067: the select camera's turn
// (client/render/select_turn.h) on a camera with the Karus eye's offset from
// `at`, looking along +z from -z, where an absolute heading wraps at +-pi.
// RQ-086: the select hall's characters, spot and info text
// (client/render/select_hall.h) in both front-clip modes, 1097's hover and
// 1298's loop, on synthetic clip lengths. RQ-087: 1298's recorded camera
// paths (client/render/select_path.h) on synthetic keys. RQ-095: the select
// zone's fog and its BLEND meshes' far-to-near order (client/render/select_zone.h).
// RQ-101: the logo screen's timeline, alpha and music (client/render/front_logo.h)
// on 1264's groups and fade. RQ-102: a loaded package's worded messages are
// printed for tests/front_end.py. RQ-106: a loaded package named ok-placed*
// prints each layout's node rects in window pixels at KO's window sizes, an
// odd size and one smaller than the canvas (client/assets/front_place.h), for
// tests/front_end.py to check against KO's own placements. RQ-108: the login
// screen's state-bound nodes in each of the realm's login states
// (client/render/front_login.h), as 1264's SetVisibleLogInUIs shows them;
// RQ-123: after a Back to the realm list without the line, and the viewer's
// Back hold (BackHold) through a session's login, a failure, a drop, a logout.
// RQ-111: the message box's styles, keys and answers (client/render/message_box.h)
// as 1298's CUIMessageBox shows and answers an OK box and the yes/no exit.
// RQ-116: a loaded package whose select ESC presses exit is printed.
// RQ-126: a loaded package's create slide (client/render/front_slide.h), run
// on its placed create layout at three window sizes and four frame times from
// the open to the lead's arrival, each frame's node coordinates printed for
// tests/front_end.py to check against 1298's Tick (00606450) as it reads.
// RQ-130: create's race and class choices (client/render/create_choice.h) as
// 1298's in-select create takes its race and class clicks (00604f90, 005fd120)
// and refuses its Create (005fffd0), and a create that binds neither.
#include "assets/assets.h"
#include "assets/front_place.h"
#include "render/create_choice.h"
#include "render/front_login.h"
#include "render/front_logo.h"
#include "render/front_slide.h"
#include "render/message_box.h"
#include "render/select_bar.h"
#include "render/select_hall.h"
#include "render/select_path.h"
#include "render/select_turn.h"
#include "render/select_zone.h"
#include <algorithm>
#include <cmath>
#include <iomanip>
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

bool near(float a, float b) { return std::abs(a - b) < 1e-3f; }

// Ticks `seconds` of the hall at rest on `focus` (or turning, focus < 0) at
// 30 ticks a second.
void run(n3e::front::SelectHall &hall, int focus, bool over, float seconds) {
  for (int i = 0; i < int(seconds * 30 + .5f); ++i)
    if (focus < 0) hall.turning(3, 1 / 30.f);
    else hall.rest(focus, 3, over, .5f, .6f, 1 / 30.f);
}

std::string hall_check() {
  using namespace n3e::front;
  SelectHall hall;
  hall.length = {2, 3, .5f};
  hall.blends = {.3f, .6f, .25f};
  // Hover (1097, 0043f280): only the character in front moves, by the pointer.
  hall.mode = n3e::FrontClipMode::hover;
  hall.reset();
  for (const auto &p : hall.players)
    if (p.loop || p.clip != kFrontClip) return "hover: AddChr's clip is not the front clip once";
  run(hall, 0, false, 1);
  if (hall.players[0].clip != kRestClip || hall.theta != 0 || hall.spot_on || hall.info_slot != -1)
    return "hover: the pointer away does not rest the character in front";
  if (hall.players[1].elapsed != 0 || hall.players[2].elapsed != 0) return "hover: a character not in front moved";
  run(hall, 0, true, 3);
  if (hall.players[0].clip != kFrontClip || !near(hall.played(hall.players[0]), 2) || !near(hall.theta, .5f) ||
      !hall.spot_on || hall.info_slot != 0)
    return "hover: the pointer over does not play the front clip once and hold it";
  const float before = hall.players[0].elapsed;
  run(hall, -1, false, 1);
  if (hall.spot_on || !near(hall.theta, .5f) || hall.players[0].elapsed != before)
    return "hover: the turn moved a character or kept the spot on";
  run(hall, 0, false, 1);
  if (hall.players[0].clip != kRestClip || !near(hall.theta, 0) || hall.spot_on)
    return "hover: the spot does not narrow to off when the pointer leaves";
  // Loop (1298, 005fef90): the character in front loops the front clip and
  // the others play the rest clip once, whatever the pointer does.
  hall.mode = n3e::FrontClipMode::loop;
  hall.reset();
  for (const auto &p : hall.players)
    if (!p.loop || p.clip != kFrontClip || p.blend != 0) return "loop: AddChr's clip is not the front clip looping";
  run(hall, 0, false, 5);
  if (hall.players[0].clip != kFrontClip || !hall.players[0].loop || !near(hall.played(hall.players[0]), 1))
    return "loop: the character in front does not loop the front clip";
  for (int i : {1, 2})
    if (hall.players[size_t(i)].clip != kRestClip || !near(hall.played(hall.players[size_t(i)]), .5f) ||
        hall.ended(hall.players[size_t(i)]) != true)
      return "loop: a character not in front does not play the rest clip once";
  if (!near(hall.theta, .5f) || !hall.spot_on || hall.info_slot != 0)
    return "loop: the spot and the info text do not show without the pointer";
  run(hall, 0, true, .5f);
  if (hall.players[0].clip != kFrontClip || !near(hall.played(hall.players[0]), 1.5f) || !near(hall.theta, .5f))
    return "loop: the pointer changed the character in front or the spot";
  if (hall.ended(hall.players[0])) return "loop: a looping clip ended";
  run(hall, -1, false, 1);
  for (const auto &p : hall.players)
    if (p.clip != kRestClip || p.loop) return "loop: the turn does not play the rest clip on everyone";
  if (!near(hall.players[0].elapsed, 1) || !near(hall.players[0].blend, .25f) || !near(hall.players[0].from_time, 1.5f))
    return "loop: the turn does not blend the character in front from its looping clip";
  if (hall.spot_on || !near(hall.theta, .5f) || hall.info_slot != -1)
    return "loop: the turn kept the spot or the info text on, or reset the spot";
  run(hall, 1, false, 1.f / 30);
  if (hall.players[1].clip != kFrontClip || !hall.players[1].loop || !near(hall.players[1].blend, .3f) ||
      hall.players[0].clip != kRestClip || hall.info_slot != 1)
    return "loop: the new character in front does not blend into the looping front clip";
  // The start (005fe7c0): the start clip once with its blend, then IsAnimEnd.
  hall.start(1, .5f);
  if (hall.players[1].clip != kStartClip || hall.players[1].loop || !hall.spot_on) return "loop: the start";
  for (int i = 0; i < 107; ++i) hall.starting(1, 1 / 30.f);
  if (hall.ended(hall.players[1])) return "loop: the start clip ended before its blend and length";
  for (int i = 0; i < 3; ++i) hall.starting(1, 1 / 30.f);
  if (!hall.ended(hall.players[1])) return "loop: the start clip did not end";
  return "";
}

bool near_v(const n3e::V &a, const n3e::V &b) {
  return near(a[0], b[0]) && near(a[1], b[1]) && near(a[2], b[2]);
}

std::string path_check() {
  using namespace n3e::front;
  n3e::FrontPath p;
  // Eye keys 0, 30 and 60 along x at 30 a second (three keys, 3 frames, a
  // tenth of a second); at keys at 15 a second, one, so the last frame is the
  // eye's (KO takes the longest key set).
  p.eye_rate = 30;
  p.eye = {{0, 1, 2}, {30, 1, 2}, {60, 1, 2}};
  p.at_rate = 15;
  p.at = {{5, 5, 5}};
  if (!near(path_frames(p), 3)) return "the path's last frame is not the longest key set's count x rate / 30";
  // DataGet: key 1 at frame 1, half-way to key 2 at 1.5, the last key blends
  // toward itself, the count gives the last key, past it nothing.
  if (!near_v(*path_key(p.eye, 30, 1), {30, 1, 2}) || !near_v(*path_key(p.eye, 30, 1.5f), {45, 1, 2}) ||
      !near_v(*path_key(p.eye, 30, 2.5f), {60, 1, 2}) || !near_v(*path_key(p.eye, 30, 3), {60, 1, 2}) ||
      path_key(p.eye, 30, 4).has_value())
    return "a key set is not sampled as CN3AnimKey::DataGet samples it";
  // 15 keys a second: key i covers frames 2i to 2i + 2.
  const std::vector<n3e::V> slow{{0, 0, 0}, {10, 0, 0}};
  if (!near_v(*path_key(slow, 15, 1), {5, 0, 0})) return "a 15-a-second key set is not blended over two frames";
  PathCamera camera;
  camera.start(p);
  if (camera.ended() || !near_v(camera.eye, {0, 1, 2}) || !near_v(camera.at, {5, 5, 5}))
    return "a started path is not on its first frame";
  // The first tick takes its load's step too (005fa670 ticks the path once).
  camera.tick(1 / 60.f);
  if (!near(camera.frame, 1) || !near_v(camera.eye, {30, 1, 2})) return "the first tick does not take two steps";
  camera.tick(1 / 60.f);
  if (!near(camera.frame, 1.5f) || !near_v(camera.eye, {45, 1, 2}) || camera.ended())
    return "a tick does not take 30 frames a second";
  camera.tick(1);
  if (!camera.ended() || camera.frame != camera.whole || !near_v(camera.eye, {60, 1, 2}))
    return "the path does not stay on its last frame";
  camera.tick(1);
  if (!camera.ended() || !near_v(camera.eye, {60, 1, 2})) return "the path moved past its last frame";
  camera.start(p);
  camera.finish();
  if (!camera.ended() || !near_v(camera.eye, {60, 1, 2})) return "a skip does not put the camera on the last frame";
  return "";
}
}  // namespace

// RQ-095: D3DFOG_LINEAR from the eye (1298's 50 to 500 m), and the alpha
// flush's far-to-near order of the zone's BLEND meshes, ties in file order,
// the opaque ones left out.
std::string zone_check() {
  using namespace n3e::front;
  if (fog_factor(0, 50, 500) != 1 || fog_factor(50, 50, 500) != 1) return "fogged before its start";
  if (std::abs(fog_factor(275, 50, 500) - .5f) > 1e-6f) return "not linear between start and end";
  if (fog_factor(500, 50, 500) != 0 || fog_factor(900, 50, 500) != 0) return "not whole fog from its end";
  auto mesh = [](uint32_t flags, n3e::V sort) {
    n3e::FrontZoneMesh z;
    z.mesh.flags = flags;
    z.sort = sort;
    return z;
  };
  using M = n3e::FrontMesh;
  const std::vector<n3e::FrontZoneMesh> zone{
      mesh(M::CUT_ZERO, {100, 0, 0}), mesh(M::BLEND, {1, 0, 0}), mesh(M::BLEND | M::UNLIT, {0, 0, 9}),
      mesh(M::BLEND, {0, 3, 0}),      mesh(M::BLEND, {-3, 0, 0}),  mesh(M::CUT_ZERO | M::UNLIT, {50, 0, 0})};
  const auto order = far_to_near(zone, {0, 0, 0});
  if (order != std::vector<size_t>{2, 3, 4, 1}) return "BLEND meshes not far to near, ties in file order";
  if (!far_to_near({zone[0], zone[5]}, {0, 0, 0}).empty()) return "an opaque mesh in the alpha pass";
  return "";
}

// RQ-101: 1264's logo (KO-FINDINGS 9.2): groups of 1.5, 1 and 1.5 s to the
// peak 1.5 (each fading in over its seconds, holding as long, fading out as
// long), the music 1 s in and its 4 s fade from group 2; KO's alpha in
// 255ths; the login after 12 s.
std::string logo_check() {
  using namespace n3e::front;
  n3e::FrontLogo logo;
  logo.groups = {{1, 1.5f, 1.5f, 1.5f}, {4, 1, 1, 1}, {7, 1.5f, 1.5f, 1.5f}};
  logo.music = 0, logo.music_delay = 1, logo.fade_group = 2, logo.fade = 4;
  auto at = [&](double t, int group, float alpha) {
    const auto f = logo_frame(logo, t);
    return f.group == group && !f.done && std::abs(f.alpha - alpha) < 1e-6f;
  };
  if (std::abs(logo_length(logo) - 12) > 1e-9 || std::abs(logo_group_start(logo, 2) - 7.5) > 1e-9)
    return "1264's logo is not 12 s, group 2 from 7.5 s";
  if (!at(0, 0, 0) || !at(.75, 0, 127 / 255.f) || !at(1.5, 0, 1) || !at(2.9, 0, 1) || !at(3.75, 0, 127 / 255.f))
    return "group 0 does not fade in over 1.5 s, hold 1.5 s and fade out over 1.5 s";
  if (!at(4.5, 1, 0) || !at(5, 1, 127 / 255.f) || !at(6, 1, 1) || !at(7.4, 1, 25 / 255.f) || !at(9, 2, 1))
    return "groups 1 and 2 do not follow";
  if (!logo_frame(logo, 12).done || logo_frame(logo, 12).group != -1 || logo_frame(logo, 11.99).done)
    return "the logo does not end at 12 s";
  if (logo_music_on(logo, .99) || !logo_music_on(logo, 1) || logo_music_gain(logo, 7.5) != 1)
    return "the music does not start 1 s in at full gain";
  if (std::abs(logo_music_gain(logo, 9.5) - .5f) > 1e-6f || logo_music_on(logo, 11.5) || logo_music_gain(logo, 11.6))
    return "the music does not fade out linearly over 4 s from group 2";
  logo.fade_group = n3e::FrontLogo::kNone, logo.fade = 0;
  if (!logo_music_on(logo, 11.9) || logo_music_gain(logo, 11.9) != 1) return "music without a fade does not play on";
  logo.music = n3e::FrontLogo::kNone;
  if (logo_music_on(logo, 5)) return "a logo without music plays";
  // Q82: only a press during the screen skips it (1264's DirectInput press
  // edge). Shown at 5 s, a focus gain at 7 s (SDL nanoseconds).
  constexpr uint64_t s = 1'000'000'000;
  if (logo_key_skips(0, 0, 3 * s, false)) return "a key before the first frame skips the logo";
  if (logo_key_skips(5 * s, 0, 4 * s, false)) return "a key stamped before the screen started skips it";
  if (!logo_key_skips(5 * s, 0, 5 * s, false) || !logo_key_skips(5 * s, 0, 6 * s, true))
    return "a key or modifier pressed during the screen does not skip it";
  if (logo_key_skips(5 * s, 7 * s, 7 * s, true) || logo_key_skips(5 * s, 7 * s, 7 * s + 50'000'000, true))
    return "a modifier right after a focus gain skips the logo";
  if (!logo_key_skips(5 * s, 7 * s, 7 * s, false)) return "a key right after a focus gain does not skip it";
  if (!logo_key_skips(5 * s, 7 * s, 7 * s + 200'000'000, true))
    return "a modifier pressed well after a focus gain does not skip it";
  return "";
}

// RQ-112, RQ-123 (KO-FINDINGS 9.12): the viewer's hold for a select Back that
// lands on the realm list (client/render/front_login.h BackHold), frame by
// frame: what each step leaves of the bar and the line held hidden, and
// whether it reports the connection's failure. Empty when every case holds.
std::string back_hold_check() {
  using H = n3e::front::BackHold;
  using F = H::Frame;
  // connected, failed, started, session, listed
  const F connecting{false, false, false, false, true}, up{true, false, false, false, true},
      session{true, false, true, true, true}, done = session, idle{true, false, true, false, true},
      failed{false, true, false, false, true}, select{true, false, true, true, false};
  struct Step { F frame; bool bar, line, failure; };
  struct Case { const char *name; bool realms; std::vector<Step> steps; bool reset_after; };
  const std::vector<Case> cases{
      // The login's Back (the realm's): nothing held.
      {"login", false, {{connecting, false, false, false}, {session, false, false, false}}, false},
      // A stored session: the bar to the flow's start, the line on to the
      // list and until it is left for the select.
      {"session", true,
       {{connecting, true, true, false}, {up, true, true, false}, {session, false, true, false},
        {done, false, true, false}, {done, false, true, false}, {select, false, false, false},
        {done, false, false, false}},
       false},
      // No stored session: the flow idles, the bar returns and the line too
      // ends (a later login press shows it, as 1264's SetVisibleLogInUIs).
      {"no session", true, {{connecting, true, true, false}, {idle, false, false, false}}, false},
      // A refused session: its login, then idle.
      {"refused", true, {{up, true, true, false}, {session, false, true, false}, {idle, false, false, false}}, false},
      // A logout's answer (Flow::Phase::logout): the flow has started, not on
      // a session's login.
      {"logout", true, {{connecting, true, true, false}, {idle, false, false, false}}, false},
      // A connection that fails while the bar is held: reported once, both end.
      {"failure", true, {{connecting, true, true, false}, {failed, false, false, true}, {failed, false, false, false}},
       false},
      // A failure after the flow started is the viewer's drop, not the hold's.
      {"late failure", true, {{session, false, true, false}, {failed, false, true, false}}, false},
      // A drop (the viewer's reset_connection): both end.
      {"drop", true, {{session, false, true, false}}, true},
      {"drop while connecting", true, {{connecting, true, true, false}}, true},
  };
  for (const auto &c : cases) {
    H hold;
    hold.back(c.realms);
    if (hold.bar_hidden() != c.realms || hold.line_hidden() != c.realms) return std::string(c.name) + ": the click";
    for (size_t i = 0; i < c.steps.size(); ++i) {
      const auto &s = c.steps[i];
      const bool failure = hold.update(s.frame) == H::Step::failed;
      if (hold.bar_hidden() != s.bar || hold.line_hidden() != s.line || failure != s.failure)
        return std::string(c.name) + ": step " + std::to_string(i) + ": bar " + std::to_string(hold.bar_hidden()) +
               " line " + std::to_string(hold.line_hidden()) + " failure " + std::to_string(failure);
    }
    if (c.reset_after) {
      hold.reset();
      if (hold.bar_hidden() || hold.line_hidden()) return std::string(c.name) + ": the reset";
      if (hold.update(connecting) != H::Step::none || hold.bar_hidden() || hold.line_hidden())
        return std::string(c.name) + ": after the reset";
    }
  }
  // A second Back after a list re-arms it.
  H hold;
  hold.back(true);
  hold.update(session);
  hold.update(select);
  hold.back(true);
  if (!hold.bar_hidden() || !hold.line_hidden()) return "a second Back";
  return {};
}

int main(int argc, char **argv) {
  if (const auto e = logo_check(); !e.empty()) {
    std::cerr << "FAIL logo screen: " << e << "\n";
    return 1;
  }
  std::cout << "PASS logo screen: 1264's groups fade in, hold and fade out in 255ths; its music from 1 s, faded over 4 s; "
               "a key stamped before it or a modifier right after a focus gain does not skip it\n";
  if (const auto e = turn_check(); !e.empty()) {
    std::cerr << "FAIL select turn: " << e << "\n";
    return 1;
  }
  std::cout << "PASS select turn: one slot's turn each way, ended where 1097's check ends it\n";
  if (const auto e = hall_check(); !e.empty()) {
    std::cerr << "FAIL select hall: " << e << "\n";
    return 1;
  }
  std::cout << "PASS select hall: 1097's hover and 1298's loop front-clip modes\n";
  if (const auto e = path_check(); !e.empty()) {
    std::cerr << "FAIL select path: " << e << "\n";
    return 1;
  }
  std::cout << "PASS select path: 1298's camera paths, sampled and played as its CN3Camera does\n";
  if (const auto e = zone_check(); !e.empty()) {
    std::cerr << "FAIL select zone: " << e << "\n";
    return 1;
  }
  std::cout << "PASS select zone: the camera's linear range fog, the alpha parts far to near\n";
  {
    // RQ-108 (KO-FINDINGS 9.4, 1264 005c2820): idle on the login, the bar
    // and no line; a login under way (the press, the browser step, the code,
    // a stored session's login), the line and no bar, with a message box over
    // it or not; the realm list, the server group and the line (a success
    // never shows the bar again); a failure or a reset back to idle. RQ-110
    // (9.5, 1298 005f74c0): the bar hides while a login is under way whether
    // the layout has a login_closed node or not; the 1298 recipe hides its
    // line, so it then shows neither.
    // RQ-123 (9.12, 1264 005bd9b0): after a Back to the realm list, its
    // login and the list show no line (the bar and the list as ever).
    using A = n3e::FrontAction;
    struct Want { const char *state; bool login, realms, waiting, back, bar, list, line; };
    for (const auto &w : {Want{"idle", true, false, false, false, true, false, false},
                          Want{"waiting", true, false, true, false, false, false, true},
                          Want{"realm list", false, true, false, false, false, true, true},
                          Want{"realm list, waiting", false, true, true, false, false, true, true},
                          Want{"select", false, false, false, false, false, false, false},
                          Want{"select, waiting", false, false, true, false, false, false, false},
                          Want{"back, waiting", true, false, true, true, false, false, false},
                          Want{"back, realm list", false, true, true, true, false, true, false},
                          Want{"back, idle", true, false, false, true, true, false, false}}) {
      const bool bar = n3e::front::login_state_shows(A::login_group, w.login, w.realms, w.waiting, w.back),
                 list = n3e::front::login_state_shows(A::realm_group, w.login, w.realms, w.waiting, w.back),
                 line = n3e::front::login_state_shows(A::login_closed, w.login, w.realms, w.waiting, w.back),
                 other = n3e::front::login_state_shows(A::login, w.login, w.realms, w.waiting, w.back);
      if (bar != w.bar || list != w.list || line != w.line || !other) {
        std::cerr << "FAIL login states: " << w.state << ": bar " << bar << " list " << list << " line " << line
                  << " other " << other << "\n";
        return 1;
      }
    }
    std::cout << "PASS login states: the bar at rest and hidden while a login is under way, KO's line instead "
                 "then and on the realm list, neither after a Back to the realm list\n";
  }
  if (const auto e = back_hold_check(); !e.empty()) {
    std::cerr << "FAIL back hold: " << e << "\n";
    return 1;
  }
  std::cout << "PASS back hold: a Back to the realm list hides the bar until the flow starts and the line through "
               "the session's login and the list; a failure, a drop, a logout or no session ends it\n";
  {
    // RQ-109 (KO-FINDINGS 9.6, 1298 005ff920, 00607160): btn_create takes the
    // slot in focus when it is empty, else the first empty one, else none
    // (KO's row 7675); btn_delete posts its box only for a character in
    // focus at rest.
    struct Want { int focus, shown, slots, slot; };
    for (const auto &w : {Want{0, 0, 3, 0}, Want{1, 1, 3, 1}, Want{2, 1, 3, 2}, Want{0, 1, 3, 1},
                          Want{1, 2, 3, 2}, Want{2, 2, 3, 2}, Want{0, 3, 3, -1}, Want{2, 3, 3, -1},
                          Want{0, 1, 1, -1}, Want{0, 0, 1, 0}}) {
      const int slot = n3e::front::select_create_slot(w.focus, w.shown, w.slots);
      if (slot != w.slot) {
        std::cerr << "FAIL select bar: create from slot " << w.focus << " with " << w.shown << " of " << w.slots
                  << ": slot " << slot << ", want " << w.slot << "\n";
        return 1;
      }
    }
    if (!n3e::front::select_delete_posts(0, 1, true) || n3e::front::select_delete_posts(1, 1, true) ||
        n3e::front::select_delete_posts(0, 1, false) || n3e::front::select_delete_posts(0, 0, true)) {
      std::cerr << "FAIL select bar: delete's box\n";
      return 1;
    }
    std::cout << "PASS select bar: 1298's create takes the slot in focus or the first empty one, or none when "
                 "all are taken; its delete box only for a character at rest\n";
  }
  {
    // RQ-113 (KO-FINDINGS 9.6, 9.13): the realm's rule hides the arrow with
    // no neighbour; KO's (1298, 1264, 1097) draws both at every slot. The row
    // left to right is 1, 0, 2 (and 1, 0 or 0 with fewer slots).
    struct Want { bool hide, next; int focus, first, last; bool shows; };
    for (const auto &w : {Want{true, false, 1, 1, 2, false}, Want{true, true, 1, 1, 2, true},
                          Want{true, false, 0, 1, 2, true}, Want{true, true, 0, 1, 2, true},
                          Want{true, false, 2, 1, 2, true}, Want{true, true, 2, 1, 2, false},
                          Want{true, false, 0, 0, 0, false}, Want{true, true, 0, 0, 0, false},
                          Want{false, false, 1, 1, 2, true}, Want{false, true, 2, 1, 2, true},
                          Want{false, false, 0, 0, 0, true}, Want{false, true, 0, 0, 0, true}}) {
      if (n3e::front::select_arrow_shows(w.hide, w.next, w.focus, w.first, w.last) != w.shows) {
        std::cerr << "FAIL select arrows: " << (w.next ? "next" : "prev") << " at slot " << w.focus << " of "
                  << w.first << ".." << w.last << (w.hide ? " (hide)" : " (draw)") << "\n";
        return 1;
      }
    }
    std::cout << "PASS select arrows: the realm's rule hides the arrow at the end of the row, KO's draws both\n";
  }
  {
    // RQ-130 (KO-FINDINGS 9.15): 1298's create opens with no race and no
    // class (005fab40, 005ffb90); a race click chooses the race and unchooses
    // the class (00604f90 sets +0x494 to -1 on every race click), a class
    // click the class, with or without a race; the click that changes a value
    // builds the new character at the camera's slot (005fd120, +0x38c),
    // nothing without a race; Create refuses no race, then no class
    // (005fffd0's codes 7, 9). A create that binds neither keeps both chosen,
    // the character at the slot in focus. RQ-145 (Q93 (b)): a class click
    // marks its labels (006062d0); an open or a race click that builds clears
    // the marks (005fd120 shows them all), a click on the race already chosen
    // keeps them.
    using A = n3e::FrontAction;
    using M = n3e::FrontMessage;
    n3e::front::CreateChoice c;
    std::string fail;
    auto want = [&](const char *step, bool stands, int at, std::optional<M> refusal, bool race_down, bool class_down,
                    bool marked) {
      if (c.stands() != stands || (stands && c.stands_at(2) != at) || c.refusal() != refusal ||
          c.down(A::create_race) != race_down || c.down(A::create_class) != class_down || c.marked != marked)
        fail = fail.empty() ? step : fail;
    };
    c.open(true, true);
    want("open", false, -1, M::create_no_race, false, false, false);
    c.click_class(1);  // a class first: chosen, no character (no race to build)
    want("class first", false, -1, M::create_no_race, false, true, true);
    c.click_race(1);   // the race in flight from slot 1: built there; the class unchosen
    want("race", true, 1, M::create_no_class, true, false, false);
    c.click_race(2);   // the same race again: the class unchosen, not built again
    want("race again", true, 1, M::create_no_class, true, false, false);
    c.click_class(2);  // the class: built again at the camera's slot
    want("class", true, 2, std::nullopt, true, true, true);
    c.click_class(0);  // the same class: not built again
    want("class again", true, 2, std::nullopt, true, true, true);
    c.click_race(1);   // the race already chosen: the class unchosen, its marks kept (no build)
    want("race after class", true, 2, M::create_no_class, true, false, true);
    c.open(true, true);  // a reopen (Cancel, or a create the server took)
    want("reopen", false, -1, M::create_no_race, false, false, false);
    c.open(true, false);  // a race button and no class button
    c.click_race(0);
    want("race only", true, 0, std::nullopt, true, false, false);
    c.open(false, false);  // the 1097 choice: chosen from the open, at the slot in focus
    want("chosen", true, 2, std::nullopt, false, false, false);
    c.click_race(1), c.click_class(1);
    want("chosen, clicked", true, 2, std::nullopt, false, false, false);
    if (!fail.empty()) {
      std::cerr << "FAIL create choice: " << fail << "\n";
      return 1;
    }
    std::cout << "PASS create choice: 1298's create waits for its race (the class unchosen by each race click), "
                 "builds the character at the camera's slot on the click that changes a value, refuses no race "
                 "then no class, marks the clicked class until an open or a build; a create that binds neither "
                 "keeps both chosen\n";
  }
  {
    // RQ-111 (KO-FINDINGS 9.7, 1298 00527a40, 00527c60, 00526d00): exit_confirm
    // is the one yes/no box, Yes and No shown and OK hidden; every other
    // message an OK box. In a yes/no box ENTER presses Yes and ESC No; in an
    // OK box both press OK. Yes on exit_confirm leaves; No, or OK anywhere,
    // only closes; a button the box does not show does nothing.
    using A = n3e::FrontAction;
    using M = n3e::FrontMessage;
    using n3e::front::BoxKey;
    using n3e::front::BoxStyle;
    std::string fail;
    for (size_t k = 0; k < size_t(M::count); ++k) {
      const auto kind = M(k);
      const auto style = n3e::front::box_style(kind);
      const bool question = kind == M::exit_confirm;
      if ((style == BoxStyle::yes_no) != question) fail = "style of message " + std::to_string(k);
      if (n3e::front::box_shows(A::ok, style) == question || n3e::front::box_shows(A::yes, style) != question ||
          n3e::front::box_shows(A::no, style) != question || !n3e::front::box_shows(A::message, style) ||
          !n3e::front::box_shows(A::title, style))
        fail = "buttons of message " + std::to_string(k);
      const auto enter = n3e::front::box_key(style, BoxKey::enter), escape = n3e::front::box_key(style, BoxKey::escape);
      if (enter != (question ? A::yes : A::ok) || escape != (question ? A::no : A::ok) ||
          n3e::front::box_key(style, BoxKey::none) != A::none)
        fail = "keys of message " + std::to_string(k);
      for (const auto button : {A::ok, A::yes, A::no, A::none, A::message}) {
        const auto answer = n3e::front::box_press(kind, button);
        const bool shown = button != A::none && button != A::message && n3e::front::box_shows(button, style);
        if (answer.closes != shown || answer.exits != (question && button == A::yes))
          fail = "answer of message " + std::to_string(k) + " to action " + std::to_string(int(button));
      }
    }
    if (!fail.empty()) {
      std::cerr << "FAIL message box: " << fail << "\n";
      return 1;
    }
    std::cout << "PASS message box: exit_confirm's Yes and No (ENTER Yes, ESC No; Yes leaves), every other "
                 "message's OK (ENTER or ESC)\n";
  }
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
      if (fe.logo) std::cout << "logo " << release.root.filename().string() << ": " << fe.logo->nodes.size()
                             << " nodes, " << fe.logo->groups.size() << " groups, flags " << fe.logo->flags << "\n";
      // RQ-102: each worded message, by its FrontMessage index.
      for (size_t k = 0; k < fe.messages.size(); ++k)
        if (const auto &m = fe.messages[k]; m.named)
          std::cout << "message " << release.root.filename().string() << ": " << k << " title='" << m.title
                    << "' replaces=" << m.replaces << " text='" << m.text << "'\n";
      // RQ-116: a select whose ESC presses exit, not back.
      if (fe.select_escape != n3e::FrontSelectEscape::back)
        std::cout << "escape " << release.root.filename().string() << ": " << uint32_t(fe.select_escape) << "\n";
      // RQ-112: a select whose Back lands on the realm list, not the login.
      if (fe.select_back != n3e::FrontSelectBack::login)
        std::cout << "back " << release.root.filename().string() << ": " << uint32_t(fe.select_back) << "\n";
      // RQ-113: a select whose arrows both draw at the end of the row.
      if (fe.select_arrows != n3e::FrontSelectArrows::hide)
        std::cout << "arrows " << release.root.filename().string() << ": " << uint32_t(fe.select_arrows) << "\n";
      // RQ-125: a create over the hall, and each slot's create yaw.
      if (fe.create_mode != n3e::FrontCreateMode::screen) {
        std::cout << std::setprecision(9) << "create " << release.root.filename().string() << ": "
                  << uint32_t(fe.create_mode) << " yaws";
        for (const auto &slot : fe.slots) std::cout << " " << slot.create_yaw;
        std::cout << "\n";
      }
      // RQ-126: slide NAME: size=WxH dt=T nodes=N frames=x,y,..;.. on=1..0
      // (each frame's slid nodes' top-left, the last the frame the slide
      // ended) and a frame of no time that moves nothing.
      if (!fe.create_slide.nodes.empty())
        for (const auto [w, h] : {std::pair{1024, 768}, {1280, 1024}, {1600, 1200}})
          for (const double dt : {1.0 / 30, 1.0 / 60, 1.0 / 144, 0.25}) {
            const auto rects = n3e::front_layout_rects(fe, size_t(n3e::FrontScreen::create), w, h);
            n3e::front::SlideState state;
            n3e::front::slide_open(state);
            std::cout << std::setprecision(9) << "slide " << release.root.filename().string() << ": size=" << w
                      << "x" << h << " dt=" << dt << " nodes=" << fe.create_slide.nodes.size() << " frames=";
            const auto print = [&] {
              const auto at = n3e::front::slide_coordinates(fe.create_slide, rects, {w, h}, state);
              for (size_t k = 0; k < at.size(); ++k) {
                const auto &n = fe.create_slide.nodes[k];
                const auto &r = rects[n.node];
                std::cout << (k ? "," : "") << (n.axis == 0 ? at[k] : r[0]) << "," << (n.axis == 1 ? at[k] : r[1]);
              }
            };
            print();
            int frames = 0;
            while (state.on && frames < 10000) {
              n3e::front::slide_tick(fe.create_slide, rects, {w, h}, state, dt);
              std::cout << ";";
              print();
              ++frames;
              if (frames == 1) {
                // A frame of no time (the first ever, a test hook's redraw) moves nothing.
                const auto before = state.d;
                n3e::front::slide_tick(fe.create_slide, rects, {w, h}, state, 0);
                if (state.d != before) error = "a slide frame of no time moved";
              }
            }
            std::cout << " rest=";
            n3e::front::slide_rest(state);
            print();
            std::cout << "\n";
          }
      // RQ-106: placed NAME: layout=L size=WxH node=I rect=x0,y0,x1,y1
      if (release.root.filename().string().starts_with("ok-placed"))
        for (const auto [w, h] : {std::pair{1024, 768}, {1280, 1024}, {1600, 1200}, {1281, 1025}, {800, 600}}) {
          const auto [scale, ox, oy] = n3e::front_view(fe, w, h);
          for (size_t layout = 0; layout < fe.moves.size(); ++layout) {
            const auto rects = n3e::front_layout_rects(fe, layout, w, h);
            for (size_t i = 0; i < rects.size(); ++i) {
              const auto &r = rects[i];
              std::cout << std::setprecision(9) << "placed " << release.root.filename().string() << ": layout=" << layout << " size=" << w
                        << "x" << h << " node=" << i << " rect=" << ox + r[0] * scale << "," << oy + r[1] * scale
                        << "," << ox + r[2] * scale << "," << oy + r[3] * scale << "\n";
            }
          }
        }
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
