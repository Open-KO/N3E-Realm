// Spec 11 acceptance 2: the client's front-end.bin loader on the synthetic
// blobs tests/front_end.py writes. Arguments are pairs: `ok DIR` must load,
// `bad DIR` must be refused with a message (never a crash). A loaded
// package's music tracks must stream.
#include "assets/assets.h"
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

int main(int argc, char **argv) {
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
