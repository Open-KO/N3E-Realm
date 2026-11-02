#pragma once
// RQ-101 (N3FE version 9): the logo screen before the login, as front-end.bin
// describes it (content/front-end.md section 10). 1264's logo procedure
// (KO-FINDINGS 9.2, the 1264 image): its UI's tick (00601360) shows each group
// alone in turn and fades it in, holds it and fades it out; Render (00600ce0)
// draws the UI with that fade, cut to KO's 8-bit texture factor
// (trunc(value x 255) << 24), over the black clear; after the last group the
// login starts. Its procedure's tick (005fa7c0) starts the music a delay after
// its first tick and fades it out from the start of a group (004371a0: the
// volume falls linearly to 0 over the fade, 00436cd0, then the stream stops).
// No GL, file access or device calls; render/front_end.h draws it.
#include "assets/assets.h"
#include <algorithm>
#include <cmath>
#include <cstdint>

namespace n3e::front {

// The screen `t` seconds after it started: the group showing (-1 once it has
// ended), its alpha (0-1, in 255ths) and whether the screen has ended.
struct LogoFrame {
  int group = -1;
  float alpha = 0;
  bool done = true;
};
inline double logo_length(const FrontLogo &logo) {
  double total = 0;
  for (const auto &g : logo.groups) total += double(g.fade_in) + g.hold + g.fade_out;
  return total;
}
// When group `index` starts, in seconds from the screen's start.
inline double logo_group_start(const FrontLogo &logo, size_t index) {
  double at = 0;
  for (size_t i = 0; i < index && i < logo.groups.size(); ++i)
    at += double(logo.groups[i].fade_in) + logo.groups[i].hold + logo.groups[i].fade_out;
  return at;
}
inline LogoFrame logo_frame(const FrontLogo &logo, double t) {
  t = std::max(t, 0.0);
  for (size_t i = 0; i < logo.groups.size(); ++i) {
    const auto &g = logo.groups[i];
    const double length = double(g.fade_in) + g.hold + g.fade_out;
    if (t < length) {
      double a = 1;
      if (t < g.fade_in) a = t / g.fade_in;
      else if (t >= double(g.fade_in) + g.hold) a = 1 - (t - g.fade_in - g.hold) / g.fade_out;
      a = std::clamp(a, 0.0, 1.0);
      return {int(i), float(std::floor(a * 255) / 255), false};
    }
    t -= length;
  }
  return {};
}
// The music at `t`: whether it plays (from its delay until its fade-out has
// run), and its gain (1, falling linearly to 0 over the fade).
inline bool logo_music_on(const FrontLogo &logo, double t) {
  if (logo.music == FrontLogo::kNone || t < logo.music_delay) return false;
  if (logo.fade_group == FrontLogo::kNone) return true;
  return t < logo_group_start(logo, logo.fade_group) + logo.fade;
}
inline float logo_music_gain(const FrontLogo &logo, double t) {
  if (!logo_music_on(logo, t)) return 0;
  if (logo.fade_group == FrontLogo::kNone) return 1;
  const double from = logo_group_start(logo, logo.fade_group);
  return float(std::clamp(1 - (t - from) / logo.fade, 0.0, 1.0));
}

// Whether a key-down skips the screen (with SKIP_KEY; Q82). 1264 skips on a
// press seen while the screen polls: ProcessUIKeyInput (005f97a0) calls the
// UI's OnKeyPress for each key whose press state (input +0x26c) is set, and
// that state is the frame's DirectInput edge, up last poll and down this one
// (source: LocalInput.cpp, m_bKeyPresses). So a key-down stamped before the
// screen's first frame (queued while the client loaded) is no press during
// it, nor is a modifier the window system reports as already held when the
// window gains focus (SDL 3.4's Wayland keyboard enter sends one key-down per
// held Shift, Ctrl, Alt, GUI, Mode or Level 5 key, stamped right after the
// focus gain). Times are SDL's event nanoseconds; 0: not drawn, no focus gain.
constexpr uint64_t kLogoFocusModifierNs = 100'000'000;
inline bool logo_key_skips(uint64_t shown_ns, uint64_t focus_ns, uint64_t key_ns, bool modifier) {
  if (shown_ns == 0 || key_ns < shown_ns) return false;
  return !(modifier && focus_ns != 0 && key_ns >= focus_ns && key_ns - focus_ns <= kLogoFocusModifierNs);
}

}  // namespace n3e::front
