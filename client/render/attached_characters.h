#pragma once
#include "assets/assets.h"
#include <algorithm>
#include <array>
#include <map>
#include <set>
#include <utility>
#include <vector>

namespace n3e {
// N3AT attached characters (PQ-328, D-186): a model on an equipped appearance
// key, placed on the wearer's joint, playing its own clip for the wearer's
// state and lit by a pulse. The rule is the 2233 client's CPlayerWing (a
// 2233/2145 addition; KO 1298 has none): CPlayerBase::Tick (0057b3a0, at
// 0057bc53) calls 0056a710 for every player that has one, which places each
// attached character on its player joint and picks its clip, and 00569590,
// which advances ONE timer per player (+0x5bc) inside its loop over the two
// slots, so with both slots attached the pulse runs twice as fast. Which
// items attach what, on which joint, how they light and whether the clock
// advances per attachment is package data; this header only evaluates it.
struct AttachedCharacters {
  struct Shade {
    std::array<float, 3> emissive{};
    float modulate = 1;
    float intensity = 0;
  };
  // One clock per wearer: KO's CPlayerWing timer (+0x5bc) and intensity
  // (+0x5c0), from 0 when the wearer is first drawn; `total` is every advance
  // summed (harness capture timing only).
  // `drawn` is the seconds the wearer has been drawn with any attachment
  // (harness capture timing; a wearer with skeletal plugs alone has no pulse).
  struct Clock {
    double t = 0, total = 0, last = -1, drawn = 0;
    float intensity = 0;
    bool seen = false;
  };
  // A skeletal plug's playing clip (PQ-317): its model slot and whether it
  // plays once and holds its end; slot -1 before its first frame.
  struct PlugState {
    int slot = -1;
    bool once = false;
    bool operator==(const PlugState &) const = default;
  };
  const Attachments *table = nullptr;
  std::map<uint32_t, size_t> by_key;
  std::map<uint64_t, Clock> clocks;
  std::set<std::pair<uint64_t, size_t>> drawn, shown;

  void build(const Attachments &a) {
    table = &a;
    by_key.clear();
    clocks.clear();
    drawn.clear();
    shown.clear();
    for (size_t i = 0; i < a.entries.size(); ++i) by_key[a.entries[i].key] = i;
  }
  bool empty() const { return !table; }

  // The entries a wearer's appearance keys attach: one per group, the entry
  // of the key that comes last in the list (KO's attach to an occupied slot
  // replaces the character there, 00568d80; the cosslot readers attach in
  // slot order), in group order (00569590 walks slot 0 then slot 1).
  template <class Keys>
  std::vector<size_t> resolve(const Keys &keys) const {
    std::map<uint32_t, size_t> groups;
    if (!table) return {};
    for (auto key : keys) {
      auto found = by_key.find(key);
      if (found != by_key.end()) groups[table->entries[found->second].group] = found->second;
    }
    std::vector<size_t> out;
    for (const auto &[group, entry] : groups) out.push_back(entry);
    return out;
  }

  // One advance of the KO timer (00569590): t += dt; while t <= rise the
  // intensity is t / rise; past hold and up to fall it falls from 1 to 0
  // (KO: 1 - (t - 3) x 0.5, floored at 0); past period t restarts at 0; in
  // between the intensity keeps its last value.
  static void step(Clock &c, const Attachments &a, double dt) {
    c.t += dt;
    c.total += dt;
    if (c.t <= a.rise) c.intensity = float(c.t / a.rise);
    else if (c.t > a.hold && c.t <= a.fall)
      c.intensity = a.fall > a.hold ? std::max(0.f, float(1 - (c.t - a.hold) / (a.fall - a.hold))) : 0.f;
    else if (c.t > a.period) c.t = 0;
  }

  // The wearer was drawn this frame with `entries` resolved: advances its
  // clock once per entry (per_attachment, as both KO slots do) or once, and
  // returns each entry's shade, in order. Optional entries hidden by the
  // client option are still passed: KO's timer runs for slot 0 whether or
  // not it is drawn (00569590 does not read the option).
  std::vector<Shade> advance(uint64_t wearer, const std::vector<size_t> &entries, double now) {
    std::vector<Shade> out;
    if (!table) return out;
    auto &c = clocks[wearer];
    c.seen = true;
    const double dt = c.last < 0 ? 0 : std::max(0., now - c.last);
    c.last = now;
    if (!entries.empty()) c.drawn += dt;
    // A skeletal plug (PQ-317) is not a CPlayerWing slot: it neither takes
    // nor advances the pulse (00569590 walks the two wing slots only). Its
    // glow is its key's equipment glow (N3E3, 0056ea30 -> 0042de90 ->
    // 00430f40), which the viewer applies to the whole model (PQ-337).
    const bool pulsed = std::any_of(entries.begin(), entries.end(),
                                    [&](size_t i) { return !(table->entries[i].flags & Attachment::PLUG); });
    if (!table->per_attachment && pulsed) step(c, *table, dt);
    for (auto i : entries) {
      const auto &e = table->entries[i];
      Shade s;
      if (e.flags & Attachment::PLUG) {
        out.push_back(s);
        continue;
      }
      if (table->per_attachment) step(c, *table, dt);
      s.intensity = c.intensity;
      s.modulate = e.modulate;
      if (e.flags & Attachment::EMISSIVE)
        for (int k = 0; k < 3; ++k) s.emissive[k] = table->color[k] * c.intensity;
      out.push_back(s);
    }
    return out;
  }

  // The attached clip for the wearer's pose state (client/render/player_pose.h:
  // 0 idle, 1 run, 2 attack, 3 death, 4 walk, 5 backward, 6 ready, 7-9 sit):
  // idle 0, walk 1, attack 2, death 3, the looks model's four clips. KO picks
  // clip 0 while moving, 1 standing or sitting, 3 attacking, 5 dead (and 2
  // struck, which n3e has no state for; 0056a710's switch at 0056a8e8); the
  // cook maps those KO clips onto these four.
  static int clip_state(int pose) {
    switch (pose) {
      case 1: case 4: case 5: return 1;
      case 2: return 2;
      case 3: return 3;
      default: return 0;
    }
  }

  // A skeletal plug's clip after this frame (PQ-317, D-187, D-188), for the
  // wearer's drawn clip (`kind`, `id`: the casting skill's animation, else the
  // combat clip or pose state it is drawn with). 2233: the plug starts clip 0
  // when it loads (00449d78); each frame the parent's clip goes through
  // 0042df00 to 00432760, which keeps the playing clip when the index is the
  // same and ignores an index past the table, and once a clip starts its
  // once flag stays until another starts. The map's row for the drawn clip
  // names the slot; a new slot restarts with the row's once flag; the same
  // slot, or a clip with no row, keeps what plays. Applied to every wearer:
  // 2233 does so only for the local player (D-188).
  static PlugState plug_clip(const Attachment &e, uint32_t kind, uint32_t id, PlugState current) {
    if (current.slot < 0) current = {0, false};
    for (const auto &row : e.clip_map)
      if (row.kind == kind && row.id == id) {
        if (int(row.slot) != current.slot) current = {int(row.slot), row.once};
        break;
      }
    return current;
  }

  // A pair drawn this frame; true the first frame it is drawn (harness).
  bool draw(uint64_t wearer, size_t entry) {
    drawn.insert({wearer, entry});
    return shown.insert({wearer, entry}).second;
  }

  // Ends each pair not drawn since the last call, and the clock of each
  // wearer not drawn: KO's player object, and its CPlayerWing, go with the
  // player. Returns the ended pairs.
  std::vector<std::pair<uint64_t, size_t>> retire() {
    std::vector<std::pair<uint64_t, size_t>> gone;
    for (auto it = shown.begin(); it != shown.end();) {
      if (!drawn.contains(*it)) {
        gone.push_back(*it);
        it = shown.erase(it);
      } else {
        ++it;
      }
    }
    drawn.clear();
    for (auto it = clocks.begin(); it != clocks.end();) {
      if (!it->second.seen) it = clocks.erase(it);
      else it->second.seen = false, ++it;
    }
    return gone;
  }
};
}
