#pragma once
#include <algorithm>
#include <array>
#include <cstdint>
#include <string>

// Curve XP can differ from lifetime XP after an explicit legacy conversion.
struct ProgressView {
  uint64_t earned, needed;
  bool capped;
  float fraction() const {
    return capped ? 1.f : std::clamp(float(earned) / needed, 0.f, 1.f);
  }
  std::string text() const {
    return capped ? "MAX" : std::to_string(earned) + "/" + std::to_string(needed);
  }
};
inline ProgressView progress_view(const std::array<uint64_t, 10> &thresholds,
                                 uint64_t level, uint64_t curve_xp) {
  level = std::clamp<uint64_t>(level, 1, thresholds.size());
  auto low = thresholds[level - 1];
  return {curve_xp - std::min(curve_xp, low),
          level == thresholds.size() ? 0 : thresholds[level] - low,
          level == thresholds.size()};
}
