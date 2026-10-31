#pragma once
// Keyboard target selection and continuous movement (PQ-009). KO client
// KnightOnLine.exe; addresses are the binary evidence for each rule.
#include "network/world.h"
#include <cstdint>
#include <limits>
#include <set>
namespace n3e::targeting {
// Slain NPCs whose death presentation has finished: n3e's counterpart of KO's
// state 5 (+0x2fc). A death puts an NPC in state 4 with next state 5
// (005cf620 -> 0045acc0; 0045a2c0 case 4); the animation tick requests the next
// state when the dying clip ends (00457d90, 00457e57-00457e62). The manager
// tick reaches that animation tick through the NPC's own tick (00470a73 slot
// +0x3c -> 004647a0 -> 00458580 at 00464e71 -> 00457d90 at 00458780) and, in the
// same loop pass, moves an NPC in state 5 from the NPC map +0x28 to the corpse
// map +0x48 (00470b25-00470b9c, PQ-172, PQ-199). Only the corpse pick (00471990)
// reads that map, so the actor pick (004724c0) and B (004711b0) count a slain
// NPC while it is dying and never once its clip has ended. The viewer fills
// the set every frame from the poses it draws (PickFrame::corpses).
using Corpses = std::set<uint64_t>;
inline float distance2(const WorldState &w, const Entity &e) {
  float dx = e.x() - w.predicted[0], dy = e.y() - w.predicted[1], dz = e.z() - w.predicted[2];
  return dx * dx + dy * dy + dz * dz;
}
// Nearest actor by 3-D distance among those `eligible` accepts; ties go to the
// lower ID so a selection never depends on snapshot order. 0 when none.
template <class F> uint64_t nearest(const WorldState &w, F eligible) {
  uint64_t best = 0;
  float best_d = std::numeric_limits<float>::max();
  for (const auto &e : w.world.entities()) {
    if (e.id() == w.world.self() || !eligible(e)) continue;
    float d = distance2(w, e);
    if (d < best_d || (d == best_d && e.id() < best)) best_d = d, best = e.id();
  }
  return best;
}
// Z (005d93f0 -> 00471f10): nearest living actor the hostility predicate
// (006164c0) accepts. n3e has no player-versus-player rules, so its hostile
// actors are exactly the living NPCs.
inline uint64_t enemy(const WorldState &w) {
  return nearest(w, [](const Entity &e) { return e.npc() && e.health(); });
}
// X (005d9500 -> 0051ba50): nearest party member other than the player; 0 with
// no party or no member in view.
inline uint64_t party_member(const WorldState &w) {
  return nearest(w, [&](const Entity &e) {
    if (e.npc()) return false;
    for (const auto &m : w.party.members())
      if (m.entity() == e.id()) return true;
    return false;
  });
}
// B (005d9600 -> 004711b0): nearest actor of NPC race (100, set for every actor
// the NPC-in handler 005cd620 creates) in the NPC map (004711b4). Unlike Z it
// has no hostility or living test (no +0x2fc read), so a dying NPC counts; a
// corpse does not, since it has left the NPC map (`Corpses`, PQ-199).
inline uint64_t npc(const WorldState &w, const Corpses &corpses) {
  return nearest(w, [&](const Entity &e) { return e.npc() && !corpses.contains(e.id()); });
}
// Z keeps the current target when nothing qualifies (005d93f0 selects only a
// found actor); X and B pass their result to the selection call (005d9ce0) even
// when it is 0, which clears the target and stops auto-attack.

// E: continuous forward movement (005d6380 -> 00466730 toggles the flag at
// player+0xae4; 005d6430 starts or stops the walk/run). The input handler
// (005c6990) accepts E only with no forward/backward key and no left button
// held; releasing a forward/backward key stops the movement, and turning keeps
// it. Dead actors cannot start it (005d6380 returns in states 4 and 5).
struct AutoMove {
  bool active = false;
  // E pressed. Returns whether the press was accepted.
  bool toggle(bool living, bool move_key, bool left_button) {
    if (move_key || left_button || !living) return false;
    active = !active;
    return true;
  }
  // Every frame: a forward/backward key ends it, as does death.
  void update(bool living, bool forward_or_back) {
    if (!living || forward_or_back) active = false;
  }
};
} // namespace n3e::targeting
