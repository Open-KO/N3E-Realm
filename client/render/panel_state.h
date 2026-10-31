#pragma once
#include <array>
#include <filesystem>
#include <fstream>
#include <map>
#include <openssl/sha.h>
#include <sstream>
#include <string>

// Client-local saved HUD panel positions for one server/game/account/character,
// the counterpart of the supplied client's per-account registry records
// (writer 00645ea0 at normal exit, restore 00647210). Never server state.
struct PanelState {
  std::string identity;
  std::filesystem::path file;
  static constexpr unsigned limit = 8;
  // Returns the saved positions for a new identity; empty when unchanged or absent.
  bool context(const std::string &scope) {
    if (identity == scope) return false;
    identity = scope; file.clear();
    const char *base = std::getenv("XDG_STATE_HOME");
    std::filesystem::path root;
    if (base && *base && std::filesystem::path(base).is_absolute()) root = base;
    else if (const char *home = std::getenv("HOME"); home && *home) root = std::filesystem::path(home) / ".local/state";
    if (root.empty()) return true;
    unsigned char digest[SHA256_DIGEST_LENGTH];
    SHA256(reinterpret_cast<const unsigned char *>(scope.data()), scope.size(), digest);
    std::string key;
    for (auto b : digest) { key += "0123456789abcdef"[b >> 4]; key += "0123456789abcdef"[b & 15]; }
    file = root / "n3e/panels" / (key + ".txt");
    return true;
  }
  std::map<std::string, std::array<int, 2>> load() const {
    std::map<std::string, std::array<int, 2>> out;
    std::error_code ec;
    auto size = std::filesystem::file_size(file, ec);
    if (file.empty() || ec || size > 4096) return out;
    std::ifstream in(file);
    std::string line;
    if (!std::getline(in, line) || line != "N3P1") return out;
    while (std::getline(in, line)) {
      std::istringstream row(line);
      std::string key; long x, y; char extra;
      // Malformed files are ignored as a whole: defaults are always safe.
      if (!(row >> key >> x >> y) || (row >> extra) || key.size() > 32 ||
          key.find_first_not_of("abcdefghijklmnopqrstuvwxyz_") != std::string::npos ||
          x < -16384 || x > 16384 || y < -16384 || y > 16384 || out.size() >= limit ||
          !out.emplace(key, std::array<int, 2>{int(x), int(y)}).second)
        return {};
    }
    return out;
  }
  bool save(const std::map<std::string, std::array<int, 2>> &positions) const {
    if (file.empty() || positions.empty()) return true;
    std::error_code ec;
    std::filesystem::create_directories(file.parent_path(), ec);
    auto tmp = file; tmp += ".tmp";
    {
      std::ofstream out(tmp, std::ios::trunc);
      out << "N3P1\n";
      for (const auto &[key, p] : positions) out << key << ' ' << p[0] << ' ' << p[1] << '\n';
      out.close();
      if (!out) return false;
    }
    std::filesystem::rename(tmp, file, ec);
    return !ec;
  }
};
