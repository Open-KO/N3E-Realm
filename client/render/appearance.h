#pragma once
#include "assets/assets.h"
#include <array>
#include <set>
#include <span>
#include <tuple>
#include <type_traits>

namespace n3e {
// RQ-221: the face and hair a player draws (its Entity face and hair), by
// number into render detail's looks parts; a number past a set draws none.
struct Looks {uint32_t face=0,hair=0;};
// World and portrait use the same composition. Unknown cosmetic keys leave the
// default body intact; a missing low-detail part falls back to its highest mesh.
// `draw` takes (mesh, indices), or (mesh, indices, key) with key 0 for the
// default body and the appearance key for each selected mesh (PQ-315).
// RQ-207: a selected key's N3DH entry hides the keys it names (a worn lower
// under a robe): they draw no mesh and hide no default-body part. A key that
// hides is hidden by none (the reader's rule), so the order does not matter.
// RQ-221: after the default body, `looks`' face and hair parts (key 0, as
// the body), as KO's InitFace and InitHair set the numbered part (1298
// 005c87c0; source PlayerOther.cpp); a set whose slot a selected key
// replaces draws none, as KO sets no hair under a helmet.
// The keys drawn (zero-based) and the default-body texture slots they hide.
struct AppearanceSelection {std::set<unsigned> selected, hidden;};
template<class Keys>
AppearanceSelection select_appearance(const RenderDetail& detail, const std::vector<AppearanceRule>& rules,
                                      const Keys& keys) {
  std::set<unsigned> selected, slots, hidden, covered;
  for (auto key : keys) {
    if (!key || key > rules.size() || key > detail.appearances.size()) continue;
    if (!slots.insert(rules[key-1].slot).second) continue;
    selected.insert(key-1);
  }
  for (auto key : selected) for (auto other : detail.appearances[key].hides) covered.insert(other-1);
  for (auto key : covered) selected.erase(key);
  for (auto key : selected)
    for (auto texture : detail.appearances[key].replaces) hidden.insert(texture);
  return {std::move(selected), std::move(hidden)};
}
// RQ-221: whether the face and the hair draw for `keys` and `looks`.
inline std::array<bool,2> looks_drawn(const RenderDetail& detail, const std::set<unsigned>& hidden, Looks looks) {
  auto drawn=[&](const LooksParts& set,uint32_t number){return number<set.parts.size()&&!hidden.contains(set.slot);};
  return {drawn(detail.faces,looks.face),drawn(detail.hairs,looks.hair)};
}
template<class Keys, class Draw>
void draw_appearance(const RenderDetail& detail, const std::vector<AppearanceRule>& rules,
                     const Keys& keys, unsigned level, Draw draw, Looks looks = {}) {
  const auto [selected, hidden] = select_appearance(detail, rules, keys);
  const auto& base=detail.levels.at(level);
  std::vector<uint32_t> indices;
  for(size_t i=0;i<base.scene.indices.size();i+=3) {
    // Material assignment is per triangle, validated by the package reader.
    if(!hidden.contains(base.slots.at(base.scene.indices[i])))
      indices.insert(indices.end(),base.scene.indices.begin()+i,base.scene.indices.begin()+i+3);
  }
  auto call=[&](const auto& mesh,std::span<const uint32_t> span,uint32_t key){
    if constexpr(std::is_invocable_v<Draw&,decltype(mesh),std::span<const uint32_t>,uint32_t>)draw(mesh,span,key);
    else draw(mesh,span);
  };
  call(base,std::span<const uint32_t>(indices),0);
  const auto drawn=looks_drawn(detail,hidden,looks);
  for(const auto& [set,number,on]:{std::tuple{&detail.faces,looks.face,drawn[0]},std::tuple{&detail.hairs,looks.hair,drawn[1]}}) {
    if(!on)continue;
    const auto& levels=set->parts[number];
    const auto& mesh=levels.at(level).scene.indices.empty()?levels.front():levels.at(level);
    call(mesh,std::span<const uint32_t>(mesh.scene.indices),0);
  }
  for(auto key:selected) {
    const auto& levels=detail.appearances[key].levels;
    const auto& mesh=levels.at(level).scene.indices.empty()?levels.front():levels.at(level);
    if(mesh.scene.indices.empty())continue;  // a skeletal plug's key (PQ-317): no rigid mesh
    call(mesh,std::span<const uint32_t>(mesh.scene.indices),key+1);
  }
}
}
