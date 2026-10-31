#pragma once
#include "assets/assets.h"
#include <array>
#include <cmath>
#include <map>
#include <optional>
#include <utility>
#include <vector>

namespace n3e {
// N3E3 equipment glow (PQ-315): an emissive colour and texture modulate on an
// equipped appearance key's geometry. The rule is the 2233 client's (a
// 2233/2145 addition; the 1298 client has none): CPlayerBase::Tick (0057b3a0)
// calls 0056ea30 for every player each tick, which advances one timer per
// player and, for each equipped part or hand plug whose item asks for it,
// writes the material emissive (the pulse or 1.0) and the stage-0 MODULATE or
// MODULATE2X choice that CN3CPart::Render (0042cf30) then draws. Which items
// glow, and how, is package data; this header only evaluates the record.
struct EquipmentGlow {
  struct Shade {
    std::array<float, 3> emissive{};
    float modulate = 1;
    float intensity = 0;
  };
  struct State {
    bool seen = false;
    double sampled = -1e9;
  };
  std::map<uint32_t, const AppearanceGlow *> records;
  // One clock per actor, as 0056ea30 keeps one timer per player (+0x454):
  // the time the actor was first drawn.
  std::map<uint64_t, std::pair<double, bool>> clocks;
  std::map<std::pair<uint64_t, uint32_t>, State> states;

  void build(const Effects &effects) {
    records.clear();
    clocks.clear();
    states.clear();
    for (const auto &g : effects.glow) records[g.key] = &g;
  }

  // The intensity at `t` seconds of the actor's clock. KO: t <= 1 rises as t,
  // 1..3 holds, 3..5 falls as 1 - (t - 3) x 0.5, 5..5.5 holds, and the timer
  // restarts once past 5.5 (0056ea30's constants).
  static float intensity(const AppearanceGlow &g, double t) {
    if (g.wave == AppearanceGlow::STEADY) return 1;
    double c = std::fmod(t, double(g.period));
    if (c < 0) c += g.period;
    if (c <= g.rise) return float(c / g.rise);
    if (c <= g.hold) return 1;
    if (c <= g.fall) return g.fall > g.hold ? float(1 - (c - g.hold) / (g.fall - g.hold)) : 0.f;
    return 0;
  }

  double clock(uint64_t actor, double now) {
    auto [it, inserted] = clocks.try_emplace(actor, now, true);
    it->second.second = true;
    return now - it->second.first;
  }

  // The shade of `key` on `actor` this frame, or nothing when the key has no
  // glow. `started` is set the first frame the pair is drawn.
  std::optional<Shade> shade(uint64_t actor, uint32_t key, double now, bool *started = nullptr) {
    auto found = records.find(key);
    double t = clock(actor, now);
    if (found == records.end()) return {};
    const auto &g = *found->second;
    auto [it, inserted] = states.try_emplace({actor, key});
    it->second.seen = true;
    if (started) *started = inserted;
    Shade s;
    s.intensity = intensity(g, t);
    for (int k = 0; k < 3; ++k) s.emissive[k] = g.color[k] * s.intensity;
    s.modulate = g.modulate;
    return s;
  }

  // True once per `every` seconds for each drawn pair (harness sampling).
  bool sample(uint64_t actor, uint32_t key, double now, double every) {
    auto it = states.find({actor, key});
    if (it == states.end() || now - it->second.sampled < every) return false;
    it->second.sampled = now;
    return true;
  }

  // Drops each pair not drawn since the last call, and the clock of each actor
  // not drawn: KO's player object, and its timer, go with the player.
  std::vector<std::pair<uint64_t, uint32_t>> retire() {
    std::vector<std::pair<uint64_t, uint32_t>> gone;
    for (auto it = states.begin(); it != states.end();) {
      if (!it->second.seen) {
        gone.push_back(it->first);
        it = states.erase(it);
      } else {
        it->second.seen = false;
        ++it;
      }
    }
    for (auto it = clocks.begin(); it != clocks.end();) {
      if (!it->second.second) it = clocks.erase(it);
      else it->second.second = false, ++it;
    }
    return gone;
  }
};
}
