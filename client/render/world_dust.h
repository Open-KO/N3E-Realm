#pragma once
// RQ-203 (Q120): the dust overlay KO's world puts on a worn item by its
// durability. The durability setter (1298 0045d5f0, 1097 004535a0; the
// source's CPlayerBase::DurabilitySet) takes the item's durability x 100 /
// its maximum and sets, on the hand's plug or the armour slot's part,
// Misc\Dust_Hard.dxt below 31, Misc\Dust_Soft.dxt below 71 and no overlay
// from 71 on; the part and plug draws (1298 00412570, 004137d0) then modulate
// the lit, textured colour by the overlay on the mesh's own UVs, alpha left
// the mesh's. In n3e the textures and the keys that draw them are package data
// (effects.bin N3E6, content/presentation-events.md); the percent is the
// server's (Entity.appearance_durability, from committed equipment).
#include "assets/assets.h"
#include <algorithm>
#include <cstdint>

namespace n3e {
// 0 the hard dust (below 31 %), 1 the soft (below 71 %), -1 none.
inline int world_dust(uint32_t percent) { return percent < 31 ? 0 : percent < 71 ? 1 : -1; }
// The dust `key` draws on a player wearing `keys` (Entity.appearance) at
// `durability` (Entity.appearance_durability, one per key in its order; empty
// from a server before RQ-203, drawn as 100): the first listing of `key`
// decides, as draw_appearance draws the first key per slot. -1 when the
// package's dust does not cover the key or the player does not wear it.
template <class Keys, class Durability>
int worn_dust(const AppearanceDust &dust, const Keys &keys, const Durability &durability, uint32_t key) {
  if (!dust.covers(key)) return -1;
  int i = 0;
  for (const uint32_t worn : keys) {
    if (worn == key) {
      const uint32_t percent = i < int(durability.size()) ? std::min<uint32_t>(durability[i], 100) : 100;
      return world_dust(percent);
    }
    ++i;
  }
  return -1;
}
}  // namespace n3e
