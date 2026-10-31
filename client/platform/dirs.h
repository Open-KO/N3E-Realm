#pragma once
// The player's config and state directories (spec 04 "Build"): the XDG base
// directories on Linux, %APPDATA% and %LOCALAPPDATA% on Windows. Empty when the
// variables are unset or not absolute; callers then keep nothing on disk.
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <string>
namespace n3e::dirs {
namespace detail {
inline std::filesystem::path env(const char *name) {
#ifdef _WIN32
  // Wide, so a profile path outside the ANSI code page survives.
  const std::wstring wide(name, name + std::strlen(name));
  const wchar_t *value = _wgetenv(wide.c_str());
#else
  const char *value = std::getenv(name);
#endif
  if (!value || !*value)
    return {};
  std::filesystem::path path(value);
  return path.is_absolute() ? path : std::filesystem::path{};
}
} // namespace detail
// Settings and the session token: $XDG_CONFIG_HOME, $HOME/.config; %APPDATA%.
inline std::filesystem::path config() {
#ifdef _WIN32
  return detail::env("APPDATA");
#else
  if (auto base = detail::env("XDG_CONFIG_HOME"); !base.empty())
    return base;
  if (auto home = detail::env("HOME"); !home.empty())
    return home / ".config";
  return {};
#endif
}
// Hotbars and panel positions: $XDG_STATE_HOME, $HOME/.local/state; %LOCALAPPDATA%.
inline std::filesystem::path state() {
#ifdef _WIN32
  return detail::env("LOCALAPPDATA");
#else
  if (auto base = detail::env("XDG_STATE_HOME"); !base.empty())
    return base;
  if (auto home = detail::env("HOME"); !home.empty())
    return home / ".local/state";
  return {};
#endif
}
} // namespace n3e::dirs
