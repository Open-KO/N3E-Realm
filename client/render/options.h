#pragma once
#include "platform/dirs.h"
#include <algorithm>
#include <cctype>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <optional>
#include <string>

// Client-local options, the counterpart of KO's Option.Ini. KO reads it once at
// start with GetPrivateProfileIntA (0064b9b0) and changes it only through its
// external options program, after which the client restarts; n3e likewise reads
// one INI file at start and has no in-game options page (PQ-048). Never server
// state, and never a privilege: it only switches local presentation.
//
// The file is $XDG_CONFIG_HOME/n3e/Option.ini, else ~/.config/n3e/Option.ini;
// %APPDATA%\n3e\Option.ini on Windows (platform/dirs.h).
// Keys this client reads, with KO's defaults:
//   [WeaponEffect] EffectVisible=1   equipped-item effects (PQ-211, 006e268e)
// and one of n3e's own, for a later client's addition (KO 1298 has no such key):
//   [Addition2233] EquipmentGlow=1   the 2233 client's equipment glow (PQ-315,
//                                    N3E3); 2233 draws it with no switch, and
//                                    only a package cooked with it carries it
//   [Addition2233] HDR=0             the 2233 client's screen bloom and tone
//                                    map (PQ-316, postprocess.bin); off unless
//                                    set, since it relights the whole scene
//                                    away from the 1298 look; 2233's own switch
//                                    is its options window (btn_state_hdr)
// and one of the 2233 client's own (PQ-328), for its attached characters:
//   [Effect] Wing=1                  draws the optional attachments (N3AT;
//                                    2233 draws CPlayerWing slot 0 only while
//                                    its global 00cf2e6d is set, which WinMain
//                                    009dfda0 reads from this key with default
//                                    1, 009e0883; slot 1 always draws)
// and KO 1298's sound switch (RQ-071, Q70):
//   [Sound] Effect=1                 every sound n3e plays: the voices and
//                                    the front end's music. 1298 creates each
//                                    sound object through 0044d240 (or plays
//                                    one once through 0044d660), which marks
//                                    it inaudible (+0x38) while the manager's
//                                    effect flag (+0x29) is clear, and
//                                    006453b0 clears that flag when this key
//                                    is 0 (0064b9b0, default 1); 004501b0 and
//                                    0044fdf0 start nothing inaudible. Off,
//                                    the client opens no audio device.
//   [Sound] Bgm is not read: 1298 applies it only to the zone music
//   (00640b10 sets the stream's +0x38 from it), which n3e does not play; the
//   front end's track is created through 0044d240 (005f68e0) and follows
//   Effect, not Bgm.
struct ClientOptions {
  bool weapon_effects = true;
  bool equipment_glow = true;
  bool hdr = false;
  bool wing = true;
  bool sound = true;

  static std::filesystem::path path() {
    auto base = n3e::dirs::config();
    return base.empty() ? base : base / "n3e/Option.ini";
  }
  // GetPrivateProfileInt's reading: section and key names compare without
  // case, the value is its leading decimal integer (0 when it has none), and a
  // missing file, section or key gives the default. A file over 64 KiB or one
  // that cannot be read gives every default.
  static std::optional<long> integer(const std::filesystem::path &file, const std::string &section, const std::string &key) {
    std::error_code ec;
    auto size = std::filesystem::file_size(file, ec);
    if (file.empty() || ec || size > 65536) return {};
    std::ifstream in(file);
    if (!in) return {};
    auto lower = [](std::string s) {
      std::transform(s.begin(), s.end(), s.begin(), [](unsigned char c) { return char(std::tolower(c)); });
      return s;
    };
    auto trim = [](std::string s) {
      auto a = s.find_first_not_of(" \t\r"), b = s.find_last_not_of(" \t\r");
      return a == std::string::npos ? std::string() : s.substr(a, b - a + 1);
    };
    std::string line, current;
    while (std::getline(in, line)) {
      line = trim(line);
      if (line.empty() || line[0] == ';') continue;
      if (line[0] == '[') {
        auto close = line.find(']');
        current = close == std::string::npos ? std::string() : lower(trim(line.substr(1, close - 1)));
        continue;
      }
      auto eq = line.find('=');
      if (eq == std::string::npos || current != lower(section) || lower(trim(line.substr(0, eq))) != lower(key)) continue;
      auto value = trim(line.substr(eq + 1));
      size_t at = 0;
      bool negative = false;
      if (at < value.size() && (value[at] == '-' || value[at] == '+')) negative = value[at++] == '-';
      long n = 0;
      while (at < value.size() && std::isdigit((unsigned char)value[at]) && n < 100000000) n = n * 10 + (value[at++] - '0');
      return negative ? -n : n;
    }
    return {};
  }
  static ClientOptions load(const std::filesystem::path &file = path()) {
    ClientOptions o;
    o.weapon_effects = integer(file, "WeaponEffect", "EffectVisible").value_or(1) != 0;
    o.equipment_glow = integer(file, "Addition2233", "EquipmentGlow").value_or(1) != 0;
    o.hdr = integer(file, "Addition2233", "HDR").value_or(0) != 0;
    o.wing = integer(file, "Effect", "Wing").value_or(1) != 0;
    o.sound = integer(file, "Sound", "Effect").value_or(1) != 0;
    return o;
  }
};
