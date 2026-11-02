#pragma once
// RQ-104: the clock a front-end screen's scene keeps (the login's character,
// drawn on the login and the realm list). No file access, threads, device or
// GL calls.
//
// KO 1097 and 1264 make the login's character again in each login Init and
// set its clip from its first frame (1264, binary: 005bd9b0 creates it and
// calls 0044fa20(0, 0, FLT_MIN, 0, 1) at 005bdb3c, which puts the frame at
// the clip's start; 1097: 00447e30 at 00523e2e), and the login tick advances it by the frame
// time (1264: 0044c330 at 005be533, whose 0044c750 adds the frame time times
// the clip's rate; 1097: the call at 005248f2). The login's track starts on
// that tick too on a process's first login, so the two keep time; a return
// (a new Init) restarts the character at its first frame.
//
// So the clock starts at 0 on the first frame that shows the scene after one
// that did not (the login or the realm list after any other screen, the
// first frame, or a return from the world), and runs on across the screens
// that share the scene, by the frame time. While a device plays the screen's
// own restarting track the clock is held to what the listener hears of it
// (HeardMusic): within the block the device has taken and is playing, from
// its start to its end. The heard position moves only when the device takes
// a block, so the clock runs on the frame time inside that window, and is
// moved only as far as the window's edge when it leaves it: even steps, none
// backwards, never past the end of the block the device is playing. The scene and the track restart together
// and keep time through a stall the device runs dry over. When the track is
// no longer heard (the device closed) the clock runs on from where it was.
#include "assets/music.h"
#include <algorithm>
#include <cstdint>

namespace n3e::front {
struct SceneClock {
  // `scene`: this frame shows the scene; `now`: seconds; `track`: the track
  // the screen plays (null for none); `heard`: what the device plays.
  // Returns the scene's time.
  double tick(bool scene, double now, const MusicTrack *track, const HeardMusic &heard) {
    const double dt = std::max(0.0, now - last);
    last = now;
    if (!scene) {
      shown = on_music = false;
      return seconds = 0;
    }
    if (!shown) {
      shown = true;
      on_music = false;
      entered = now;
      ++entries;
      seconds = 0;
    } else {
      seconds += dt;
    }
    if (!track || heard.track != track) {
      on_music = false;
      return seconds;
    }
    // The period started again since the last frame: count on from it.
    if (on_music && heard.seconds < was_heard - heard.period / 2) seconds -= heard.period;
    seconds = std::clamp(seconds, std::max(0.0, heard.seconds - heard.block), heard.seconds);
    was_heard = heard.seconds;
    on_music = true;
    return seconds;
  }
  // The entry's first frame, the scene's time, the last frame's `now`, the
  // heard position the last frame kept time by.
  double entered = 0, seconds = 0, last = 0, was_heard = 0;
  uint64_t entries = 0;  // the scene's entries since the clock was made
  bool shown = false, on_music = false;
};
}  // namespace n3e::front
